"""Playlist operations for YouTube API."""

# Standard library
import datetime as dt
import math
import random
import time
from typing import Any

# Third-party
import pyyoutube as pyt  # type: ignore[import-untyped]
import tqdm  # type: ignore[import-untyped]

# Local
from .. import config
from .. import file_utils
from .. import paths
from ..models import PlaylistItemRef
from . import utils


def add_to_playlist(
        service: pyt.Client,
        playlist_id: str,
        videos_list: list[str],
        prog_bar: bool = True
) -> None:
    """Add a list of video to a YouTube playlist.

    Args:
        service: A Python YouTube Client.
        playlist_id: A YouTube playlist ID.
        videos_list: List of YouTube video IDs.
        prog_bar: Whether to use tqdm progress bar.
    """
    api_failure = file_utils.load_json(str(paths.API_FAILURE_JSON))
    api_fail = False

    if prog_bar:
        add_iterator = tqdm.tqdm(videos_list, desc=f'Adding videos to the playlist ({playlist_id})')
    else:
        add_iterator = videos_list

    for video_id in add_iterator:
        r_body = {'snippet': {'playlistId': playlist_id, 'resourceId': {'kind': 'youtube#video', 'videoId': video_id}}}

        for attempt in range(config.MAX_RETRIES):
            try:
                service.playlistItems.insert(parts='snippet', body=r_body)
                break  # Success, exit retry loop

            except pyt.error.PyYouTubeException as http_error:
                try:
                    error_reason = http_error.response.json()['error']['errors'][0]['reason']
                except (KeyError, IndexError, TypeError):
                    error_reason = 'unknown'

                # Normalize error reason for comparison (API returns mixed formats: camelCase, SCREAMING_SNAKE_CASE)
                error_reason_normalized = error_reason.lower().replace('_', '')

                # Handle transient errors with exponential backoff + jitter
                if error_reason_normalized in utils.TRANSIENT_ERRORS and attempt < config.MAX_RETRIES - 1:
                    # Calculate exponential backoff with equal jitter to prevent thundering herd
                    delay = min(config.MAX_BACKOFF, int(config.BASE_DELAY * math.exp(attempt)))
                    wait_time = delay / 2 + random.uniform(0, delay / 2)
                    if utils.history:
                        utils.history.warning('Transient error (%s) for video %s, retrying in %.2fs (attempt %s/%s)',
                                              error_reason, video_id, wait_time, attempt + 1, config.MAX_RETRIES)
                    time.sleep(wait_time)
                    continue

                # Handle permanent errors - log and skip, don't save for retry
                if error_reason_normalized in utils.PERMANENT_ERRORS:
                    if utils.history:
                        utils.history.warning('Permanent error (%s) for video %s - skipping: %s',
                                              error_reason, video_id, http_error.message)
                    break  # Don't save to api_failure.json

                # Handle quota errors or failed transient retries - save for next day retry
                if utils.history:
                    utils.history.warning('Addition Request Failure: (%s) - %s - %s',
                                          video_id, error_reason, http_error.message)
                api_failure[playlist_id]['failure'].append(video_id)
                api_fail = True
                break

    if api_fail:  # Save API failure
        file_utils.save_json(str(paths.API_FAILURE_JSON), api_failure)


def del_from_playlist(
        service: pyt.Client,
        playlist_id: str,
        items_list: list[PlaylistItemRef] | list[dict[str, Any]],
        prog_bar: bool = True
) -> None:
    """Delete videos inside a YouTube playlist.

    Args:
        service: A Python YouTube Client.
        playlist_id: A YouTube playlist ID.
        items_list: List of PlaylistItemRef instances or dicts with 'item_id' and 'video_id'.
        prog_bar: Whether to use tqdm progress bar.
    """
    if prog_bar:
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
            service.playlistItems.delete(playlist_item_id=item_id)

        except pyt.error.PyYouTubeException as http_error:
            if utils.history:
                utils.history.warning('Deletion Request Failure: (%s) - %s', video_id, http_error.message)


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
        current_count = len(service.playlistItems.list(
            part=['snippet'],
            max_results=lmt,
            playlist_id=target_playlist
        ).items)
        return lmt - current_count

    except pyt.PyYouTubeException as error:
        if error.status_code == 403:
            if utils.history:
                utils.history.warning('API quota exceeded.')
        else:
            if utils.history:
                utils.history.warning('Unknown error: %s', error.message)
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
        prog_bar: bool
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
    add_to_playlist(
        service,
        target_playlist,
        [v['video_id'] for v in videos],
        prog_bar
    )
    del_from_playlist(
        service,
        source_playlist,
        videos,
        prog_bar
    )


def fill_release_radar(
        service: pyt.Client,
        target_playlist: str,
        re_listening_id: str,
        legacy_id: str,
        lmt: int | None = None,
        prog_bar: bool = True
) -> None:
    """Fill the Release Radar playlist with videos from re-listening playlists.

    Args:
        service: A Python YouTube Client.
        target_playlist: YouTube playlist ID where videos need to be added.
        re_listening_id: YouTube playlist ID for music to re-listen to.
        legacy_id: An older YouTube playlist to clear out.
        lmt: The addition threshold (uses config.RELEASE_RADAR_TARGET by default).
        prog_bar: Whether to use tqdm progress bar.
    """
    if lmt is None:
        lmt = config.RELEASE_RADAR_TARGET

    n_add = _get_videos_to_add_count(service, target_playlist, lmt)
    if n_add <= 0:
        if utils.history:
            utils.history.info('No addition necessary for Release Radar')
        return

    # Calculate proportional allocation from each source
    to_re_listen_count, legacy_count = utils.get_items_count(service, [re_listening_id, legacy_id])
    n_add_rel, n_add_leg = _calculate_allocation(n_add, to_re_listen_count, legacy_count)

    # Fetch and format videos from both playlists
    week_ago = utils.NOW - dt.timedelta(weeks=config.RELISTENING_AGE_WEEKS)

    to_re_listen_items = service.playlistItems.list(
        part=['snippet', 'contentDetails'],
        playlist_id=re_listening_id,
        max_results=lmt
    ).items
    to_re_listen_raw = [{'video_id': item.contentDetails.videoId,
                         'add_date': dt.datetime.strptime(
                             item.snippet.publishedAt,
                             utils.ISO_DATE_FORMAT
                         ),
                         'item_id': item.id} for item in to_re_listen_items]

    to_re_listen_fil = [item for item in to_re_listen_raw if item['add_date'] < week_ago]

    legacy_items = service.playlistItems.list(
        part=['contentDetails'],
        playlist_id=legacy_id,
        max_results=lmt
    ).items
    legacy_raw = [{'video_id': item.contentDetails.videoId, 'item_id': item.id} for item in legacy_items]

    # Pre-selection with fallback if one source is insufficient
    addition_rel = to_re_listen_fil[:n_add_rel]
    addition_leg = legacy_raw[:n_add_leg]

    # Adjust allocations if one source doesn't have enough content
    if len(addition_leg) < n_add_leg:
        addition_rel = to_re_listen_fil[:n_add - len(addition_leg)]

    elif len(addition_rel) < n_add_rel:
        addition_leg = legacy_raw[:n_add - len(addition_rel)]

    # Transfer videos from sources to target
    _transfer_videos(
        service,
        target_playlist,
        re_listening_id,
        addition_rel,
        'Re-listening',
        prog_bar
    )

    _transfer_videos(
        service,
        target_playlist,
        legacy_id,
        addition_leg,
        'Legacy',
        prog_bar
    )


def add_api_fail(service: pyt.Client, prog_bar: bool = True) -> None:
    """Add missing videos to a targeted playlist following API failures on a previous run.

    Args:
        service: A Python YouTube Client.
        prog_bar: Whether to use tqdm progress bar.
    """
    api_failure = file_utils.load_json(str(paths.API_FAILURE_JSON))
    addition = 0

    for p_id, info in api_failure.items():
        if info['failure']:
            videos_to_retry = info['failure'].copy()  # Copy the list before clearing
            if utils.history:
                utils.history.info('%s addition(s) to %s playlist from previous API failure.',
                                   len(videos_to_retry), info['name'])
            api_failure[p_id]['failure'] = []  # Clear before retry so add_to_playlist can re-add failures
            file_utils.save_json(str(paths.API_FAILURE_JSON), api_failure)  # Save cleared state

            # Failed videos get re-added here
            add_to_playlist(service, p_id, videos_to_retry, prog_bar=prog_bar)
            addition += 1

    if addition > 0:
        if utils.history:
            utils.history.info('Video recovery from previous API failure(s) complete.')
