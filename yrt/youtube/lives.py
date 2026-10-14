"""Music lives: detection through the channels' Live tab and update of the lives playlist.

Detection lists each channel's "Live" tab as a playlist (UULV prefix, 1 unit), then reads the live status of every
candidate with videos.list (1 unit per 50 videos). The playlist keeps live and upcoming streams (port plan D1) and
drops the rest; new streams are inserted at their rank, never twice.
"""

# Standard library
import datetime as dt
from collections import Counter
from collections.abc import Collection, Iterable, Sequence
from functools import partial
from operator import attrgetter
from typing import Any

# Third-party
import pyyoutube as pyt
import tqdm

# Local
from .. import config
from ..constants import (
    CHANNEL_PREFIX,
    LIVE_STATUS_NONE,
    LIVE_TAB_PLAYLIST_PREFIX,
    QUOTA_COST_LIST,
    QUOTA_COST_WRITE,
    STATUS_PUBLIC,
)
from ..exceptions import APIError, QuotaExhaustedError
from ..models import LiveStream, PlaylistItemRef
from . import quota, retry, utils

# videos.list parts: live status and title (snippet), viewers and start times, view count, privacy
LIVE_DETAILS_PARTS = ['snippet', 'liveStreamingDetails', 'statistics', 'status']


def live_tab_playlist_id(channel_id: str) -> str:
    """Return the playlist ID of a channel's "Live" tab.

    Args:
        channel_id: YouTube channel ID (UC...).

    Returns:
        The UULV... playlist ID.
    """
    return f'{LIVE_TAB_PLAYLIST_PREFIX}{channel_id.removeprefix(CHANNEL_PREFIX)}'


def get_live_candidates(service: pyt.Client, channel_id: str) -> list[str]:
    """List the most recent videos of a channel's "Live" tab (one page, 1 unit).

    Args:
        service: A Python YouTube Client.
        channel_id: YouTube channel ID.

    Returns:
        Video IDs, newest first; empty when the channel has no Live tab (404) or the request failed (logged).

    Raises:
        QuotaExhaustedError: If the API rejected the call for quota reasons.
    """
    playlist_id = live_tab_playlist_id(channel_id)

    try:
        response = retry.call_api(
            partial(
                service.playlistItems.list,
                part=['contentDetails'],
                playlist_id=playlist_id,
                max_results=config.API_BATCH_SIZE,
            ),
            cost=QUOTA_COST_LIST,
            description=f'playlistItems.list({playlist_id})',
        )

    except APIError as error:
        if isinstance(error, QuotaExhaustedError):
            raise
        if error.status_code != 404 and utils.history:
            utils.history.warning('Live tab of %s unavailable: %s', channel_id, error)
        return []

    return [item.contentDetails.videoId for item in response.items]


def _parse_time(value: str | None) -> dt.datetime | None:
    """Parse an API timestamp (e.g. '2026-08-27T09:12:00Z').

    Args:
        value: The timestamp, or None.

    Returns:
        A timezone-aware datetime, or None.
    """
    return dt.datetime.fromisoformat(value) if value else None


def _to_live_stream(video: Any) -> LiveStream:
    """Build a LiveStream from a videos.list item.

    Args:
        video: A video resource with the LIVE_DETAILS_PARTS parts.

    Returns:
        The stream; fields the API left out are None.
    """
    details = video.liveStreamingDetails
    return LiveStream(
        video_id=video.id,
        channel_id=video.snippet.channelId or '',
        title=video.snippet.title or '',
        status=video.snippet.liveBroadcastContent or LIVE_STATUS_NONE,
        privacy_status=(video.status.privacyStatus if video.status else None) or STATUS_PUBLIC,
        concurrent_viewers=details.concurrentViewers if details else None,
        total_views=video.statistics.viewCount if video.statistics else None,
        actual_start_time=_parse_time(details.actualStartTime if details else None),
        scheduled_start_time=_parse_time(details.scheduledStartTime if details else None),
    )


def get_live_details(service: pyt.Client, video_ids: Iterable[str]) -> dict[str, LiveStream]:
    """Read the live status of videos, 50 per call.

    Args:
        service: A Python YouTube Client.
        video_ids: YouTube video IDs (duplicates are requested once).

    Returns:
        LiveStream by video ID; deleted and private videos are absent (the API does not return them).

    Raises:
        APIError: If a request fails.
    """
    streams: dict[str, LiveStream] = {}

    for chunk in utils.chunked(list(dict.fromkeys(video_ids)), config.API_BATCH_SIZE):
        response = retry.call_api(
            partial(service.videos.list, part=LIVE_DETAILS_PARTS, video_id=chunk, max_results=config.API_BATCH_SIZE),
            cost=QUOTA_COST_LIST,
            description='videos.list(liveStreamingDetails)',
        )
        streams.update((video.id, _to_live_stream(video)) for video in response.items)

    return streams


def find_live_streams(
    service: pyt.Client,
    channels: Sequence[str],
    *,
    stale_before: dt.datetime,
    to_pass: Collection[str] = (),
    prog_bar: bool = True,
) -> list[LiveStream]:
    """Find the live and upcoming streams of a set of channels.

    Args:
        service: A Python YouTube Client.
        channels: YouTube channel IDs.
        stale_before: Upcoming streams scheduled before this time never started and are left out.
        to_pass: Channel IDs to skip.
        prog_bar: Whether to use tqdm progress bar.

    Returns:
        Current streams (live or upcoming, not private, not stale), best ranked first.

    Raises:
        QuotaExhaustedError: If the API rejected a call for quota reasons.
        APIError: If reading the candidates' status fails.
    """
    watched = [channel_id for channel_id in channels if channel_id not in to_pass]
    channel_it = tqdm.tqdm(watched, desc='Looking for live streams') if prog_bar else watched

    candidates = [video_id for channel_id in channel_it for video_id in get_live_candidates(service, channel_id)]
    streams = get_live_details(service, candidates)

    return sorted(
        (stream for stream in streams.values() if stream.is_current(stale_before)), key=attrgetter('rank_key')
    )


def cap_per_channel(streams: Iterable[LiveStream], max_per_channel: int) -> list[LiveStream]:
    """Rank streams and keep the best ones of each channel.

    Args:
        streams: Streams to rank.
        max_per_channel: Streams kept per channel, 0 for no cap.

    Returns:
        The kept streams, best ranked first.
    """
    ranked = sorted(streams, key=attrgetter('rank_key'))
    if max_per_channel <= 0:
        return ranked

    seen: Counter[str] = Counter()
    kept = []
    for stream in ranked:
        seen[stream.channel_id] += 1
        if seen[stream.channel_id] <= max_per_channel:
            kept.append(stream)
    return kept


def fetch_playlist_refs(service: pyt.Client, playlist_id: str) -> list[PlaylistItemRef]:
    """List every item of a playlist, in playlist order.

    Args:
        service: A Python YouTube Client.
        playlist_id: YouTube playlist ID.

    Returns:
        One reference per playlist item.

    Raises:
        APIError: If a page fails (a partial list would let duplicates in).
    """
    refs: list[PlaylistItemRef] = []
    next_page_token = None

    while True:
        response = retry.call_api(
            partial(
                service.playlistItems.list,
                part=['contentDetails'],
                playlist_id=playlist_id,
                max_results=config.API_BATCH_SIZE,
                pageToken=next_page_token,
            ),
            cost=QUOTA_COST_LIST,
            description=f'playlistItems.list({playlist_id})',
        )
        refs.extend(PlaylistItemRef(item_id=item.id, video_id=item.contentDetails.videoId) for item in response.items)

        next_page_token = response.nextPageToken
        if not next_page_token:
            return refs


def _insert_position(order: list[str], ranks: dict[str, int], video_id: str) -> int:
    """Position that keeps a new stream ahead of every kept stream ranked below it.

    Args:
        order: Video IDs currently in the playlist, in playlist order (items about to be removed included).
        ranks: Rank of every stream the playlist should hold.
        video_id: The stream to insert.

    Returns:
        Index of the first kept item ranked below the stream, or the end of the playlist.
    """
    rank = ranks[video_id]
    return next(
        (index for index, current in enumerate(order) if current in ranks and ranks[current] > rank),
        len(order),
    )


def _insert_at(service: pyt.Client, playlist_id: str, video_id: str, position: int) -> bool:
    """Insert a video at a position of a playlist.

    Args:
        service: A Python YouTube Client.
        playlist_id: YouTube playlist ID.
        video_id: YouTube video ID.
        position: Zero-based position.

    Returns:
        True if the video was inserted, False if the insert failed (logged).

    Raises:
        QuotaExhaustedError: If the API rejected the call for quota reasons.
    """
    body = {
        'snippet': {
            'playlistId': playlist_id,
            'position': position,
            'resourceId': {'kind': 'youtube#video', 'videoId': video_id},
        }
    }

    try:
        retry.call_api(
            partial(service.playlistItems.insert, parts='snippet', body=body),
            cost=QUOTA_COST_WRITE,
            description=f'playlistItems.insert({playlist_id})',
            video_id=video_id,
        )

    except APIError as error:
        if isinstance(error, QuotaExhaustedError):
            raise
        if utils.history:
            utils.history.warning('Live insertion failure: (%s) - %s', video_id, error)
        return False

    return True


def _delete_item(service: pyt.Client, playlist_id: str, ref: PlaylistItemRef) -> bool:
    """Delete an item from a playlist.

    Args:
        service: A Python YouTube Client.
        playlist_id: YouTube playlist ID (for the logs).
        ref: The playlist item to delete.

    Returns:
        True if the item was deleted, False if the delete failed (logged).

    Raises:
        QuotaExhaustedError: If the API rejected the call for quota reasons.
    """
    try:
        retry.call_api(
            partial(service.playlistItems.delete, playlist_item_id=ref.item_id),
            cost=QUOTA_COST_WRITE,
            description=f'playlistItems.delete({playlist_id})',
            video_id=ref.video_id,
        )

    except APIError as error:
        if isinstance(error, QuotaExhaustedError):
            raise
        if utils.history:
            utils.history.warning('Live removal failure: (%s) - %s', ref.video_id, error)
        return False

    return True


def update_lives_playlist(
    service: pyt.Client,
    playlist_id: str,
    lives: Iterable[LiveStream],
    *,
    stale_before: dt.datetime,
    max_per_channel: int = 0,
    prog_bar: bool = True,
) -> tuple[list[str], list[str]]:
    """Bring the lives playlist in line with the active streams.

    The playlist's own items are re-checked, so a stream missed by detection is only removed once it really ended.
    Adds come first and removals second, each capped to what the job's quota budget can still pay for; the next run
    picks up whatever was skipped (nothing is queued).

    Args:
        service: A Python YouTube Client.
        playlist_id: YouTube playlist ID of the lives playlist.
        lives: Current streams found by find_live_streams().
        stale_before: Upcoming streams scheduled before this time never started and are removed.
        max_per_channel: Streams kept per channel, 0 for no cap (port plan D2).
        prog_bar: Whether to use tqdm progress bar.

    Returns:
        The inserted video IDs and the removed video IDs (failed writes left out).

    Raises:
        QuotaExhaustedError: If the API rejected a call for quota reasons.
        APIError: If the playlist or its items' status cannot be read.
    """
    current = fetch_playlist_refs(service, playlist_id)
    wanted = _wanted_streams(service, current, lives, stale_before, max_per_channel)
    ranks = {stream.video_id: rank for rank, stream in enumerate(wanted)}
    to_add, to_remove = _plan_changes(current, wanted, ranks)

    # Adds run first: positions are computed against the playlist as it is, items about to be removed included
    order = [ref.video_id for ref in current]
    added = _add_streams(service, playlist_id, _affordable(to_add, 'insertion'), order, ranks, prog_bar)
    removed = _remove_items(service, playlist_id, _affordable(to_remove, 'removal'), prog_bar)

    if utils.history:
        utils.history.info('Lives playlist: %s added, %s removed.', len(added), len(removed))

    return added, removed


def _wanted_streams(
    service: pyt.Client,
    current: list[PlaylistItemRef],
    lives: Iterable[LiveStream],
    stale_before: dt.datetime,
    max_per_channel: int,
) -> list[LiveStream]:
    """Streams the playlist should hold: the detected ones plus its own items still current, ranked and capped.

    Args:
        service: A Python YouTube Client.
        current: The playlist's items.
        lives: Current streams found by find_live_streams().
        stale_before: Upcoming streams scheduled before this time never started.
        max_per_channel: Streams kept per channel, 0 for no cap.

    Returns:
        The wanted streams, best ranked first.

    Raises:
        APIError: If the status of the playlist's items cannot be read.
    """
    streams = {stream.video_id: stream for stream in lives}
    streams.update(get_live_details(service, (ref.video_id for ref in current if ref.video_id not in streams)))
    return cap_per_channel((stream for stream in streams.values() if stream.is_current(stale_before)), max_per_channel)


def _plan_changes(
    current: list[PlaylistItemRef], wanted: list[LiveStream], ranks: dict[str, int]
) -> tuple[list[str], list[PlaylistItemRef]]:
    """Split the work: wanted streams missing from the playlist, and items that must go.

    An item goes when it is ended, stale, private, deleted, over the cap, or a second copy of the same video.

    Args:
        current: The playlist's items, in playlist order.
        wanted: The wanted streams, best ranked first.
        ranks: Rank of every wanted stream.

    Returns:
        The video IDs to insert (best ranked first) and the items to remove (in playlist order).
    """
    seen: set[str] = set()
    to_remove = []
    for ref in current:
        if ref.video_id not in ranks or ref.video_id in seen:
            to_remove.append(ref)
        seen.add(ref.video_id)

    return [stream.video_id for stream in wanted if stream.video_id not in seen], to_remove


def _affordable[T](items: list[T], kind: str) -> list[T]:
    """Keep the writes the job's quota budget can still pay for, and log the postponed ones.

    Args:
        items: Writes to make, in priority order.
        kind: Kind of write, for the log ('insertion' or 'removal').

    Returns:
        The leading writes that fit in the budget.
    """
    affordable = quota.get_tracker().remaining // QUOTA_COST_WRITE
    if len(items) > affordable and utils.history:
        utils.history.warning('Quota budget reached: %s live %s(s) postponed.', len(items) - affordable, kind)
    return items[:affordable]


def _add_streams(
    service: pyt.Client,
    playlist_id: str,
    to_add: list[str],
    order: list[str],
    ranks: dict[str, int],
    prog_bar: bool,
) -> list[str]:
    """Insert streams at their rank, keeping order in step with the playlist.

    Args:
        service: A Python YouTube Client.
        playlist_id: YouTube playlist ID.
        to_add: Video IDs to insert, best ranked first.
        order: Video IDs currently in the playlist, updated after every insert.
        ranks: Rank of every wanted stream.
        prog_bar: Whether to use tqdm progress bar.

    Returns:
        The inserted video IDs.

    Raises:
        QuotaExhaustedError: If the API rejected a call for quota reasons.
    """
    added = []
    add_it = tqdm.tqdm(to_add, desc=f'Adding lives ({playlist_id})') if prog_bar else to_add
    for video_id in add_it:
        position = _insert_position(order, ranks, video_id)
        if _insert_at(service, playlist_id, video_id, position):
            order.insert(position, video_id)
            added.append(video_id)
    return added


def _remove_items(service: pyt.Client, playlist_id: str, to_remove: list[PlaylistItemRef], prog_bar: bool) -> list[str]:
    """Delete playlist items.

    Args:
        service: A Python YouTube Client.
        playlist_id: YouTube playlist ID.
        to_remove: Items to delete.
        prog_bar: Whether to use tqdm progress bar.

    Returns:
        The video IDs of the deleted items.

    Raises:
        QuotaExhaustedError: If the API rejected a call for quota reasons.
    """
    remove_it = tqdm.tqdm(to_remove, desc='Deleting from playlist') if prog_bar else to_remove
    return [ref.video_id for ref in remove_it if _delete_item(service, playlist_id, ref)]
