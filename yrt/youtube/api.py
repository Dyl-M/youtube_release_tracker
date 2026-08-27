"""Core YouTube API call functions."""

# Standard library
import datetime as dt
import itertools
from collections.abc import Collection
from functools import partial
from typing import Any

# Third-party
import pyyoutube as pyt
import tqdm

# Local
from .. import config, file_utils, paths
from ..constants import QUOTA_COST_LIST
from ..context import ExecutionContext
from ..exceptions import APIError
from ..models import AddOnConfig, PlaylistItem
from . import retry, utils


def _parse_playlist_item(item: Any, date_format: str, source_channel_id: str) -> PlaylistItem | None:
    """Parse a playlist item into a PlaylistItem dataclass, returns None if no release date.

    Args:
        item: A playlist item from YouTube API response.
        date_format: Date format string for parsing.
        source_channel_id: Channel ID being iterated (for artist channel handling).

    Returns:
        Parsed PlaylistItem or None if no release date.
    """
    if item.contentDetails.videoPublishedAt is None:
        return None

    return PlaylistItem(
        video_id=item.contentDetails.videoId,
        video_title=item.snippet.title,
        item_id=item.id,
        release_date=dt.datetime.strptime(item.contentDetails.videoPublishedAt, date_format),
        status=item.status.privacyStatus,
        channel_id=item.snippet.videoOwnerChannelId,
        channel_name=item.snippet.videoOwnerChannelTitle,
        source_channel_id=source_channel_id,  # Set at creation - no mutation!
    )


def _handle_playlist_error(error: APIError, playlist_id: str, not_found_pass: Collection[str]) -> None:
    """Handle a playlist read failure: swallow "not found" (with a warning unless whitelisted), raise anything else.

    Args:
        error: The APIError raised by the retry layer.
        playlist_id: The playlist ID that caused the error.
        not_found_pass: Channel IDs whose missing upload playlist is expected (no warning).

    Raises:
        APIError: For any failure other than a 404.
    """
    if error.status_code == 404:
        channel_id = f'UC{playlist_id[2:]}'
        if channel_id not in not_found_pass and utils.history:
            utils.history.warning('Playlist not found: %s', playlist_id)
        return

    raise retry.rewrap(error, f'[{playlist_id}] Unknown error') from error


def _filter_items_by_date_range(
    p_items: list[PlaylistItem], latest_d: dt.datetime, oldest_d: dt.datetime | None = None, day_ago: int | None = None
) -> list[PlaylistItem]:
    """Filter videos on a date range.

    Args:
        p_items: Playlist items as a list of PlaylistItem dataclasses.
        latest_d: The latest reference date.
        oldest_d: Latest execution date.
        day_ago: Day difference with a reference date, delimits items' collection field.

    Returns:
        Filtered items.
    """
    if oldest_d:
        return [item for item in p_items if oldest_d < item.release_date < latest_d]
    if day_ago:
        date_delta = latest_d - dt.timedelta(days=day_ago)
        return [item for item in p_items if date_delta < item.release_date < latest_d]
    return p_items


def get_playlist_items(
    service: pyt.Client,
    playlist_id: str,
    source_channel_id: str,
    ctx: ExecutionContext,
    *,
    day_ago: int | None = None,
    not_found_pass: Collection[str] = (),
) -> list[PlaylistItem]:
    """Get the videos in a YouTube playlist released inside the run's window.

    Args:
        service: A Python YouTube Client.
        playlist_id: A YouTube playlist ID.
        source_channel_id: Channel ID being iterated (for artist channel handling).
        ctx: Execution context; the window is (ctx.last_exe, ctx.now), both rounded down to the hour.
        day_ago: Replaces the lower bound with ctx.now minus that many days when given.
        not_found_pass: Channel IDs whose missing upload playlist is expected (no warning on 404).

    Returns:
        Playlist items as list of PlaylistItem dataclasses.

    Raises:
        APIError: If the playlist request fails for a reason other than "not found".
    """
    p_items: list[PlaylistItem] = []
    next_page_token = None

    latest_d = ctx.now.replace(minute=0, second=0, microsecond=0)
    oldest_d = None if day_ago else ctx.last_exe.replace(minute=0, second=0, microsecond=0)

    while True:
        try:
            request = retry.call_api(
                partial(
                    service.playlistItems.list,
                    part=['snippet', 'contentDetails', 'status'],
                    playlist_id=playlist_id,
                    max_results=config.API_BATCH_SIZE,
                    pageToken=next_page_token,
                ),
                cost=QUOTA_COST_LIST,
                description=f'playlistItems.list({playlist_id})',
            )

        except APIError as error:
            _handle_playlist_error(error, playlist_id, not_found_pass)  # raises unless it was a 404
            break

        # Parse items, filtering out those without release date
        for item in request.items:
            parsed = _parse_playlist_item(item, utils.ISO_DATE_FORMAT, source_channel_id)
            if parsed is not None:
                p_items.append(parsed)
        p_items = _filter_items_by_date_range(p_items, latest_d, oldest_d=oldest_d, day_ago=day_ago)

        next_page_token = request.nextPageToken

        # No need for more requests (the playlist must be ordered chronologically!)
        if len(p_items) <= config.API_BATCH_SIZE or next_page_token is None:
            break

    return p_items


def get_videos(service: pyt.Client, videos_list: list[str]) -> list[Any]:
    """Get information from YouTube videos.

    Args:
        service: A Python YouTube Client.
        videos_list: List of YouTube video IDs.

    Returns:
        Request results.

    Raises:
        APIError: If the request fails.
    """
    return retry.call_api(  # type: ignore[no-any-return]
        partial(
            service.videos.list,
            part=['snippet', 'contentDetails', 'statistics', 'status'],
            video_id=videos_list,
            max_results=config.API_BATCH_SIZE,
        ),
        cost=QUOTA_COST_LIST,
        description='videos.list',
    ).items


def get_subs(service: pyt.Client, channel_list: list[str | None]) -> list[dict[str, Any]]:
    """Get the number of subscribers for several YouTube channels.

    Args:
        service: A Python YouTube Client.
        channel_list: List of YouTube channel IDs; None entries (videos without an owner channel) are skipped.

    Returns:
        Playlist items (channels' information) as a list.

    Raises:
        APIError: If a request fails.
    """
    ch_filter = [channel_id for channel_id in channel_list if channel_id is not None]

    # Split task in chunks to request on a maximum of API_BATCH_SIZE channels at each iteration.
    raw_chunk = []

    for chunk in utils.chunked(ch_filter, config.API_BATCH_SIZE):
        req = retry.call_api(
            partial(service.channels.list, part=['statistics'], channel_id=chunk, max_results=config.API_BATCH_SIZE),
            cost=QUOTA_COST_LIST,
            description='channels.list',
        ).items
        raw_chunk += req

    return [{'channel_id': item.id, 'subscribers': item.statistics.subscriberCount} for item in raw_chunk]


def check_if_live(service: pyt.Client, videos_list: list[str]) -> list[dict[str, Any]]:
    """Get broadcast status with YouTube video IDs.

    Args:
        service: A Python YouTube Client.
        videos_list: List of YouTube video IDs.

    Returns:
        Playlist items (videos) as a list.

    Raises:
        APIError: If API error occurs while checking live status.
    """
    items = []

    # Split tasks in chunks to request a maximum of API_BATCH_SIZE videos at each iteration.
    for chunk in utils.chunked(videos_list, config.API_BATCH_SIZE):
        try:
            request = get_videos(service=service, videos_list=chunk)

            # Keep necessary data
            items += [{'video_id': video.id, 'live_status': video.snippet.liveBroadcastContent} for video in request]

        except APIError as api_error:
            raise retry.rewrap(api_error, 'API error while checking live status') from api_error

    return items


def iter_channels(
    service: pyt.Client,
    channels: list[str],
    ctx: ExecutionContext,
    add_on: AddOnConfig,
    *,
    day_ago: int | None = None,
    prog_bar: bool = True,
) -> list[PlaylistItem]:
    """Apply 'get_playlist_items' to the upload playlist of each channel.

    Args:
        service: A Python YouTube Client.
        channels: List of YouTube channel IDs.
        ctx: Execution context giving the discovery window.
        add_on: Channel filters (to_pass channels are skipped, playlist_not_found_pass ones fail silently on 404).
        day_ago: Replaces the window's lower bound with ctx.now minus that many days when given.
        prog_bar: Whether to use tqdm progress bar.

    Returns:
        PlaylistItem instances with source_channel_id set at creation (no mutation!).
    """
    # Create pairs of (channel_id, playlist_id) to track source channel
    channel_playlist_pairs = [(ch_id, f'UU{ch_id[2:]}') for ch_id in channels if ch_id not in add_on.to_pass]
    pairs_it = (
        tqdm.tqdm(channel_playlist_pairs, desc='Looking for videos to add') if prog_bar else channel_playlist_pairs
    )

    item_it = [
        get_playlist_items(service, pl_id, ch_id, ctx, day_ago=day_ago, not_found_pass=add_on.playlist_not_found_pass)
        for ch_id, pl_id in pairs_it
    ]

    return list(itertools.chain.from_iterable(item_it))


def get_items_count(service: pyt.Client, playlist_ids: list) -> tuple:
    """Get the number of videos in YouTube Playlists.

    Args:
        service: A Python YouTube Client.
        playlist_ids: List of YouTube playlist IDs.

    Returns:
        Number of videos by playlist (ordered).

    Raises:
        APIError: If the request fails.
    """
    playlists = retry.call_api(
        partial(service.playlists.list, part=['contentDetails'], playlist_id=playlist_ids),
        cost=QUOTA_COST_LIST,
        description='playlists.list',
    ).items
    return tuple(pl.contentDetails.itemCount for pl in playlists)


def sort_db(service: pyt.Client, log: bool = True) -> None:
    """Sort and save the PocketTube database file.

    Args:
        service: A Python YouTube Client.
        log: Whether to apply logging or not.
    """

    def get_channels(_service: pyt.Client, _channel_list: list[str]) -> list[str]:
        """Get YouTube channels basic information.

        Args:
            _service: A Python YouTube Client.
            _channel_list: List of YouTube channel IDs.

        Returns:
            A list of channel IDs sorted alphabetically by channel name.

        Raises:
            APIError: If API error occurs while sorting database.
        """
        information = []

        # Split task in chunks to request on a maximum of API_BATCH_SIZE channels at each iteration.
        for chunk in utils.chunked(_channel_list, config.API_BATCH_SIZE):
            try:
                # Request channels
                request = retry.call_api(
                    partial(
                        _service.channels.list, part=['snippet'], channel_id=chunk, max_results=config.API_BATCH_SIZE
                    ),
                    cost=QUOTA_COST_LIST,
                    description='channels.list',
                ).items

                # Extract upload playlists, channel names and their ID.
                information += [{'title': an_item.snippet.title, 'id': an_item.id} for an_item in request]

            except APIError as api_error:
                raise retry.rewrap(api_error, 'API error while sorting database', log=log) from api_error

        # Sort channels' name by alphabetical order
        information = sorted(information, key=lambda dic: dic['title'].lower())
        return [info['id'] for info in information]  # Get channel IDs only

    channels_db = file_utils.load_json(str(paths.POCKET_TUBE_JSON))

    categories = [db_keys for db_keys in channels_db if 'ysc' not in db_keys]  # Get PT categories
    db_sorted = {
        category: get_channels(_service=service, _channel_list=channels_db[category]) for category in categories
    }

    for category in categories:  # Rewrite categories in the dict object associated with the PT JSON file
        channels_db[category] = db_sorted[category]

    file_utils.save_json(str(paths.POCKET_TUBE_JSON), channels_db)
