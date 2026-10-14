"""Playlist operations for YouTube API."""

# Standard library
import datetime as dt
import math
from collections.abc import Sequence
from functools import partial
from typing import Any

# Third-party
import pyyoutube as pyt
import tqdm

# Local
from .. import config, file_utils, paths
from ..constants import QUOTA_COST_LIST, QUOTA_COST_WRITE
from ..context import ExecutionContext
from ..exceptions import APIError, ErrorCategory
from ..models import PlaylistItemRef
from . import retry, utils
from .api import get_items_count


def _queue_entry(playlists: dict[str, Any], playlist_id: str) -> dict[str, Any]:
    """Return the playlists.json entry holding a playlist's queues, creating it for a playlist that is not defined.

    Args:
        playlists: Parsed content of playlists.json.
        playlist_id: YouTube playlist ID.

    Returns:
        The entry dict, guaranteed to have 'failed' and 'pending' lists.
    """
    defined = (data for data in playlists.values() if isinstance(data, dict) and data.get('id') == playlist_id)
    # Unknown playlist: keyed and named by its ID
    fallback = {'name': playlist_id, 'description': '', 'id': playlist_id}
    found = next(defined, None)
    entry: dict[str, Any] = found if found is not None else playlists.setdefault(playlist_id, fallback)

    entry.setdefault('failed', [])
    entry.setdefault('pending', [])
    return entry


def add_to_playlist(service: pyt.Client, playlist_id: str, videos_list: list[str], prog_bar: bool = True) -> None:
    """Add a list of video to a YouTube playlist.

    Transient errors are retried by the retry layer; permanent errors are logged and skipped; quota errors, unknown
    errors and exhausted retries are queued in the playlist's 'failed' list (playlists.json) for the next run.

    Args:
        service: A Python YouTube Client.
        playlist_id: A YouTube playlist ID.
        videos_list: List of YouTube video IDs.
        prog_bar: Whether to use tqdm progress bar.
    """
    playlists = file_utils.load_json(str(paths.PLAYLISTS_JSON))
    api_fail = False

    if prog_bar:
        add_iterator = tqdm.tqdm(videos_list, desc=f'Adding videos to the playlist ({playlist_id})')
    else:
        add_iterator = videos_list

    for video_id in add_iterator:
        r_body = {'snippet': {'playlistId': playlist_id, 'resourceId': {'kind': 'youtube#video', 'videoId': video_id}}}

        try:
            retry.call_api(
                partial(service.playlistItems.insert, parts='snippet', body=r_body),
                cost=QUOTA_COST_WRITE,
                description=f'playlistItems.insert({playlist_id})',
                video_id=video_id,
            )

        except APIError as error:
            # Permanent errors - log and skip, don't save for retry
            if error.category is ErrorCategory.PERMANENT:
                if utils.history:
                    utils.history.warning(
                        'Permanent error (%s) for video %s - skipping: %s', error.reason, video_id, error
                    )
                continue

            # Quota errors, unknown errors and exhausted transient retries - save for next run
            if utils.history:
                utils.history.warning('Addition Request Failure: (%s) - %s - %s', video_id, error.reason, error)
            _queue_entry(playlists, playlist_id)['failed'].append(video_id)
            api_fail = True

    if api_fail:  # Save the failed queue
        file_utils.save_json(str(paths.PLAYLISTS_JSON), playlists)


def del_from_playlist(
    service: pyt.Client,
    playlist_id: str,
    items_list: Sequence[PlaylistItemRef | dict[str, Any]],
    prog_bar: bool = True,
) -> None:
    """Delete videos inside a YouTube playlist.

    Args:
        service: A Python YouTube Client.
        playlist_id: A YouTube playlist ID.
        items_list: PlaylistItemRef instances and/or dicts with 'item_id' and 'video_id' (mixing is fine).
        prog_bar: Whether to use tqdm progress bar.
    """
    if prog_bar:
        # noinspection PyTypeChecker
        del_iterator = tqdm.tqdm(items_list, desc=f'Deleting videos from the playlist ({playlist_id})')

    else:
        del_iterator = items_list

    for item in del_iterator:
        # Handle both PlaylistItemRef and dict
        if isinstance(item, PlaylistItemRef):
            item_id = item.item_id
            video_id = item.video_id
        else:
            item_id = item['item_id']
            video_id = item['video_id']

        try:
            retry.call_api(
                partial(service.playlistItems.delete, playlist_item_id=item_id),
                cost=QUOTA_COST_WRITE,
                description=f'playlistItems.delete({playlist_id})',
                video_id=video_id,
            )

        except APIError as error:
            if utils.history:
                utils.history.warning('Deletion Request Failure: (%s) - %s', video_id, error)


def _get_videos_to_add_count(service: pyt.Client, target_playlist: str, lmt: int) -> int:
    """Calculate how many videos are needed to fill the target playlist.

    Args:
        service: YouTube API client.
        target_playlist: Target playlist ID.
        lmt: Target playlist size limit.

    Returns:
        Number of videos to add (0 if error or already full).
    """
    try:
        current_count = len(
            retry.call_api(
                partial(service.playlistItems.list, part=['snippet'], max_results=lmt, playlist_id=target_playlist),
                cost=QUOTA_COST_LIST,
                description=f'playlistItems.list({target_playlist})',
            ).items
        )
        return lmt - current_count

    except APIError as error:
        if error.category is ErrorCategory.QUOTA or error.status_code == 403:
            if utils.history:
                utils.history.warning('API quota exceeded.')
        elif utils.history:
            utils.history.warning('Unknown error: %s', error)
        return 0


def _calculate_allocation(n_add: int, count_a: int, count_b: int) -> tuple[int, int]:
    """Calculate proportional allocation between two sources.

    Args:
        n_add: Total number to add.
        count_a: Item count in source A.
        count_b: Item count in source B.

    Returns:
        Tuple of (allocation_a, allocation_b).
    """
    total = count_a + count_b

    if total == 0:
        return 0, 0

    ratio_a = count_a / total
    ratio_b = count_b / total

    if ratio_a < ratio_b:
        return math.ceil(n_add * ratio_a), math.floor(n_add * ratio_b)

    return math.floor(n_add * ratio_a), math.ceil(n_add * ratio_b)


def _transfer_videos(
    service: pyt.Client,
    target_playlist: str,
    source_playlist: str,
    videos: list[dict],
    source_name: str,
    prog_bar: bool,
) -> None:
    """Transfer videos from source to target playlist.

    Args:
        service: YouTube API client.
        target_playlist: Destination playlist ID.
        source_playlist: Source playlist ID.
        videos: List of video dicts with 'video_id' and 'item_id'.
        source_name: Name for logging.
        prog_bar: Whether to display progress bar.
    """
    if not videos:
        return

    if utils.history:
        utils.history.info('%s addition(s) from %s playlist.', len(videos), source_name)
    add_to_playlist(service, target_playlist, [v['video_id'] for v in videos], prog_bar)
    del_from_playlist(service, source_playlist, videos, prog_bar)


def fill_release_radar(
    service: pyt.Client,
    target_playlist: str,
    re_listening_id: str,
    legacy_id: str,
    ctx: ExecutionContext,
    lmt: int | None = None,
    prog_bar: bool = True,
) -> None:
    """Fill the Release Radar playlist with videos from re-listening playlists.

    Args:
        service: A Python YouTube Client.
        target_playlist: YouTube playlist ID where videos need to be added.
        re_listening_id: YouTube playlist ID for music to re-listen to.
        legacy_id: An older YouTube playlist to clear out.
        ctx: Execution context; ctx.now is the reference for the re-listening age.
        lmt: The addition threshold (uses config.RELEASE_RADAR_TARGET by default).
        prog_bar: Whether to use tqdm progress bar.

    Raises:
        APIError: If reading the source playlists fails.
    """
    if lmt is None:
        lmt = config.RELEASE_RADAR_TARGET

    n_add = _get_videos_to_add_count(service, target_playlist, lmt)
    if n_add <= 0:
        if utils.history:
            utils.history.info('No addition necessary for Release Radar')
        return

    # Calculate proportional allocation from each source
    to_re_listen_count, legacy_count = get_items_count(service, [re_listening_id, legacy_id])
    n_add_rel, n_add_leg = _calculate_allocation(n_add, to_re_listen_count, legacy_count)

    # Fetch and format videos from both playlists
    week_ago = ctx.now - dt.timedelta(weeks=config.RELISTENING_AGE_WEEKS)

    to_re_listen_items = retry.call_api(
        partial(
            service.playlistItems.list, part=['snippet', 'contentDetails'], playlist_id=re_listening_id, max_results=lmt
        ),
        cost=QUOTA_COST_LIST,
        description=f'playlistItems.list({re_listening_id})',
    ).items
    to_re_listen_raw = [
        {
            'video_id': item.contentDetails.videoId,
            'add_date': dt.datetime.strptime(item.snippet.publishedAt, utils.ISO_DATE_FORMAT),
            'item_id': item.id,
        }
        for item in to_re_listen_items
    ]

    to_re_listen_fil = [item for item in to_re_listen_raw if item['add_date'] < week_ago]

    legacy_items = retry.call_api(
        partial(service.playlistItems.list, part=['contentDetails'], playlist_id=legacy_id, max_results=lmt),
        cost=QUOTA_COST_LIST,
        description=f'playlistItems.list({legacy_id})',
    ).items
    legacy_raw = [{'video_id': item.contentDetails.videoId, 'item_id': item.id} for item in legacy_items]

    # Pre-selection with fallback if one source is insufficient
    addition_rel = to_re_listen_fil[:n_add_rel]
    addition_leg = legacy_raw[:n_add_leg]

    # Adjust allocations if one source doesn't have enough content
    if len(addition_leg) < n_add_leg:
        addition_rel = to_re_listen_fil[: n_add - len(addition_leg)]

    elif len(addition_rel) < n_add_rel:
        addition_leg = legacy_raw[: n_add - len(addition_rel)]

    # Transfer videos from sources to target
    _transfer_videos(service, target_playlist, re_listening_id, addition_rel, 'Re-listening', prog_bar)

    _transfer_videos(service, target_playlist, legacy_id, addition_leg, 'Legacy', prog_bar)


def add_api_fail(service: pyt.Client, prog_bar: bool = True) -> None:
    """Add missing videos to a targeted playlist following API failures on a previous run.

    Args:
        service: A Python YouTube Client.
        prog_bar: Whether to use tqdm progress bar.
    """
    playlists = file_utils.load_json(str(paths.PLAYLISTS_JSON))
    queued = {
        key: list(info['failed'])  # Copy before clearing
        for key, info in playlists.items()
        if isinstance(info, dict) and info.get('failed')
    }
    if not queued:
        return

    # Clear every queue and save once, before any retry: add_to_playlist reloads the file and re-queues what fails
    # again, so saving this snapshot later would overwrite those re-queued videos
    for key in queued:
        playlists[key]['failed'] = []
    file_utils.save_json(str(paths.PLAYLISTS_JSON), playlists)

    for key, videos_to_retry in queued.items():
        info = playlists[key]
        if utils.history:
            utils.history.info(
                '%s addition(s) to %s playlist from previous API failure.', len(videos_to_retry), info.get('name', key)
            )
        add_to_playlist(service, info.get('id', key), videos_to_retry, prog_bar=prog_bar)  # Failed videos re-added

    if utils.history:
        utils.history.info('Video recovery from previous API failure(s) complete.')
