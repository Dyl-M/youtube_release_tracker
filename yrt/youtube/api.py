"""Core YouTube API call functions."""

# Standard library
import datetime as dt
import itertools
from typing import Any

# Third-party
import pyyoutube as pyt  # type: ignore[import-untyped]
import tqdm  # type: ignore[import-untyped]

# Local
from .. import config
from ..exceptions import APIError
from ..models import PlaylistItem
from . import utils


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
        source_channel_id=source_channel_id  # Set at creation - no mutation!
    )


def _handle_playlist_error(
        error: pyt.error.PyYouTubeException,
        playlist_id: str,
        add_on: dict[str, Any] | None = None
) -> bool:
    """Handle playlist API errors. Raises APIError for fatal errors.

    Args:
        error: The PyYouTubeException that was raised.
        playlist_id: The playlist ID that caused the error.
        add_on: Configuration dict containing playlistNotFoundPass list. Defaults to global ADD_ON.

    Returns:
        True if should break loop, False otherwise.

    Raises:
        APIError: For unrecognized API errors.
    """
    if add_on is None:
        add_on = utils.ADD_ON

    if error.status_code == 404:
        channel_id = f'UC{playlist_id[2:]}'
        if channel_id not in add_on['playlistNotFoundPass'] and utils.history:
            utils.history.warning('Playlist not found: %s', playlist_id)
        return True

    if utils.history:
        utils.history.error('[%s] Unknown error: %s', playlist_id, error.message)
    raise APIError(f'[{playlist_id}] Unknown error: {error.message}')


def _filter_items_by_date_range(
        p_items: list[PlaylistItem],
        latest_d: dt.datetime,
        oldest_d: dt.datetime | None = None,
        day_ago: int | None = None
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
        day_ago: int | None = None,
        latest_d: dt.datetime | None = None
) -> list[PlaylistItem]:
    """Get the videos in a YouTube playlist.

    Args:
        service: A Python YouTube Client.
        playlist_id: A YouTube playlist ID.
        source_channel_id: Channel ID being iterated (for artist channel handling).
        day_ago: Day difference with a reference date, delimits items' collection field.
        latest_d: The latest reference date. Defaults to NOW.

    Returns:
        Playlist items as list of PlaylistItem dataclasses.
    """
    if latest_d is None:
        latest_d = utils.NOW

    p_items: list[PlaylistItem] = []
    next_page_token = None

    latest_d = latest_d.replace(minute=0, second=0, microsecond=0)
    oldest_d = None if day_ago else utils.LAST_EXE.replace(minute=0, second=0, microsecond=0)

    while True:
        try:
            request = service.playlistItems.list(
                part=['snippet', 'contentDetails', 'status'],
                playlist_id=playlist_id,
                max_results=config.API_BATCH_SIZE,
                pageToken=next_page_token
            )

            # Parse items, filtering out those without release date
            p_items += [
                parsed
                for item in request.items
                if (parsed := _parse_playlist_item(item, utils.ISO_DATE_FORMAT, source_channel_id)) is not None
            ]
            p_items = _filter_items_by_date_range(p_items, latest_d, oldest_d=oldest_d, day_ago=day_ago)

            next_page_token = request.nextPageToken

            # No need for more requests (the playlist must be ordered chronologically!)
            if len(p_items) <= config.API_BATCH_SIZE or next_page_token is None:
                break

        except pyt.error.PyYouTubeException as error:
            if _handle_playlist_error(error, playlist_id):
                break

    return p_items


def get_videos(service: pyt.Client, videos_list: list[str]) -> list[Any]:
    """Get information from YouTube videos.

    Args:
        service: A Python YouTube Client.
        videos_list: List of YouTube video IDs.

    Returns:
        Request results.
    """
    return service.videos.list(  # type: ignore[no-any-return]
        part=['snippet', 'contentDetails', 'statistics', 'status'],
        video_id=videos_list,
        max_results=config.API_BATCH_SIZE
    ).items


def get_subs(service: pyt.Client, channel_list: list[str]) -> list[dict[str, Any]]:
    """Get the number of subscribers for several YouTube channels.

    Args:
        service: A Python YouTube Client.
        channel_list: List of YouTube channel IDs.

    Returns:
        Playlist items (channels' information) as a list.
    """
    ch_filter = [channel_id for channel_id in channel_list if channel_id is not None]

    # Split task in chunks to request on a maximum of API_BATCH_SIZE channels at each iteration.
    batch_size = config.API_BATCH_SIZE
    channels_chunks = [ch_filter[i:i + min(batch_size, len(ch_filter))] for i in range(0, len(ch_filter), batch_size)]
    raw_chunk = []

    for chunk in channels_chunks:
        req = service.channels.list(part=['statistics'], channel_id=chunk, max_results=config.API_BATCH_SIZE).items
        raw_chunk += req

    items = [{'channel_id': item.id, 'subscribers': item.statistics.subscriberCount} for item in raw_chunk]

    return items


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
    batch_size = config.API_BATCH_SIZE
    videos_chunks = [videos_list[i:i + min(batch_size, len(videos_list))]
                     for i in range(0, len(videos_list), batch_size)]

    for chunk in videos_chunks:
        try:
            request = get_videos(service=service, videos_list=chunk)

            # Keep necessary data
            items += [{'video_id': video.id, 'live_status': video.snippet.liveBroadcastContent} for video in request]

        except pyt.error.PyYouTubeException as api_error:
            if utils.history:
                utils.history.error(api_error.message)
            raise APIError(f'API error while checking live status: {api_error.message}')

    return items


def iter_channels(
        service: pyt.Client,
        channels: list[str],
        day_ago: int | None = None,
        latest_d: dt.datetime | None = None,
        prog_bar: bool = True
) -> list[PlaylistItem]:
    """Apply 'get_playlist_items' for a collection of YouTube playlists.

    Args:
        service: A Python YouTube Client.
        channels: List of YouTube channel IDs.
        day_ago: Day difference with a reference date, delimits items' collection field.
        latest_d: The latest reference date. Defaults to NOW.
        prog_bar: Whether to use tqdm progress bar.

    Returns:
        PlaylistItem instances with source_channel_id set at creation (no mutation!).
    """
    if latest_d is None:
        latest_d = utils.NOW

    # Create pairs of (channel_id, playlist_id) to track source channel
    channel_playlist_pairs = [(ch_id, f'UU{ch_id[2:]}') for ch_id in channels if ch_id not in utils.ADD_ON['toPass']]

    if prog_bar:
        item_it = [
            get_playlist_items(service, pl_id, ch_id, day_ago, latest_d)
            for ch_id, pl_id in tqdm.tqdm(channel_playlist_pairs, desc='Looking for videos to add')
        ]

    else:
        item_it = [
            get_playlist_items(service, pl_id, ch_id, day_ago, latest_d)
            for ch_id, pl_id in channel_playlist_pairs
        ]

    return list(itertools.chain.from_iterable(item_it))
