"""Cleanup functions for YouTube playlists."""

# Standard library
import datetime as dt
from collections.abc import Callable
from functools import partial
from typing import Any

# Third-party
import pyyoutube as pyt

# Local
from .. import config
from ..constants import LIVE_STATUS_NONE, QUOTA_COST_LIST
from ..context import ExecutionContext
from ..exceptions import APIError, ErrorCategory
from ..models import PlaylistConfig, PlaylistItemRef
from . import retry, utils
from .api import get_videos
from .playlist import del_from_playlist


def _is_quota_error(error: APIError) -> bool:
    """Tell whether an APIError is a quota rejection (by category, or by the historical 403 heuristic).

    Args:
        error: The error raised by the retry layer.

    Returns:
        True for quota errors.
    """
    return error.category is ErrorCategory.QUOTA or error.status_code == 403


def _paginate_playlist_items(
    service: pyt.Client,
    playlist_id: str,
    playlist_name: str,
    check_label: str,
    transform: Callable[[Any], PlaylistItemRef | None],
) -> list[PlaylistItemRef]:
    """Page through a playlist, keeping what transform() returns; stop with partial results on API errors.

    Args:
        service: A Python YouTube Client.
        playlist_id: The playlist ID to fetch items from.
        playlist_name: The playlist name for logging.
        check_label: What the caller is checking, for the quota warning (e.g. 'retention', 'streams').
        transform: Maps one API item to a PlaylistItemRef, or None to skip it.

    Returns:
        The kept PlaylistItemRef instances, possibly partial if a page failed (logged as a warning).
    """
    kept: list[PlaylistItemRef] = []
    next_page_token = None

    while True:
        try:
            response = retry.call_api(
                partial(
                    service.playlistItems.list,
                    part=['snippet', 'contentDetails'],
                    playlist_id=playlist_id,
                    max_results=config.API_BATCH_SIZE,
                    pageToken=next_page_token,
                ),
                cost=QUOTA_COST_LIST,
                description=f'playlistItems.list({playlist_id})',
            )

        except APIError as error:
            if _is_quota_error(error):
                if utils.history:
                    utils.history.warning('API quota exceeded while checking %s for %s', check_label, playlist_name)
            elif utils.history:
                utils.history.warning('Error fetching items from %s: %s', playlist_name, error)
            break

        kept.extend(ref for item in response.items if (ref := transform(item)) is not None)

        next_page_token = response.nextPageToken
        if not next_page_token:
            break

    return kept


def _fetch_stream_playlist_items(service: pyt.Client, playlist_id: str, playlist_name: str) -> list[PlaylistItemRef]:
    """Fetch all items from a stream playlist with pagination.

    Args:
        service: A Python YouTube Client.
        playlist_id: The playlist ID to fetch items from.
        playlist_name: The playlist name for logging.

    Returns:
        List of PlaylistItemRef instances with item_id and video_id.
    """
    return _paginate_playlist_items(
        service,
        playlist_id,
        playlist_name,
        'streams',
        lambda item: PlaylistItemRef(item_id=item.id, video_id=item.contentDetails.videoId),
    )


def _fetch_expired_items(
    service: pyt.Client, playlist_id: str, playlist_name: str, cutoff_date: dt.datetime
) -> list[PlaylistItemRef]:
    """Fetch items from a playlist that are older than the cutoff date.

    Args:
        service: A Python YouTube Client.
        playlist_id: The playlist ID to fetch items from.
        playlist_name: The playlist name for logging.
        cutoff_date: Items added before this date are considered expired.

    Returns:
        List of PlaylistItemRef instances for expired items.
    """

    def expired_ref(item: Any) -> PlaylistItemRef | None:
        """Keep the item only if it was added to the playlist before the cutoff (snippet.publishedAt)."""
        added_date_str = item.snippet.publishedAt
        if not added_date_str:
            return None

        added_date = dt.datetime.strptime(added_date_str, utils.ISO_DATE_FORMAT)
        if added_date >= cutoff_date:
            return None

        return PlaylistItemRef(item_id=item.id, video_id=item.contentDetails.videoId, add_date=added_date)

    return _paginate_playlist_items(service, playlist_id, playlist_name, 'retention', expired_ref)


def _find_ended_streams(service: pyt.Client, all_items: list[PlaylistItemRef]) -> list[PlaylistItemRef]:
    """Find streams that have ended by checking their live status.

    Args:
        service: A Python YouTube Client.
        all_items: List of PlaylistItemRef instances.

    Returns:
        List of PlaylistItemRef instances where the stream has ended.
    """
    video_ids = [item.video_id for item in all_items]
    video_id_to_item = {item.video_id: item for item in all_items}
    ended_items: list[PlaylistItemRef] = []

    # Batch video status checks
    for chunk in utils.chunked(video_ids, config.API_BATCH_SIZE):
        try:
            videos_response = get_videos(service=service, videos_list=chunk)
            for video in videos_response:
                if video.snippet.liveBroadcastContent == LIVE_STATUS_NONE and video.id in video_id_to_item:
                    ended_items.append(video_id_to_item[video.id])

        except APIError as error:
            if utils.history:
                utils.history.warning('Error checking stream status: %s', error)

    return ended_items


def cleanup_expired_videos(
    service: pyt.Client, playlist_config: dict[str, PlaylistConfig], ctx: ExecutionContext, prog_bar: bool = True
) -> None:
    """Remove expired videos from playlists with retention rules.

    For each playlist with 'retention_days' configured:
        1. Fetch all items from the playlist.
        2. Filter items where snippet.publishedAt < (ctx.now - retention_days).
        3. Delete expired items using del_from_playlist().

    Args:
        service: A Python YouTube Client.
        playlist_config: Dictionary of PlaylistConfig instances.
            Each playlist may have retention_days configured.
        ctx: Execution context; ctx.now is the reference for the retention cutoff.
        prog_bar: Whether to use tqdm progress bar.
    """
    for playlist_cfg in playlist_config.values():
        if playlist_cfg.retention_days is None:
            continue

        playlist_id = playlist_cfg.id
        playlist_name = playlist_cfg.name
        cutoff_date = ctx.now - dt.timedelta(days=playlist_cfg.retention_days)

        if utils.history:
            utils.history.info(
                'Checking retention for playlist "%s" (retention: %d days)', playlist_name, playlist_cfg.retention_days
            )

        expired_items = _fetch_expired_items(service, playlist_id, playlist_name, cutoff_date)

        if expired_items:
            if utils.history:
                utils.history.info('Removing %d expired video(s) from "%s"', len(expired_items), playlist_name)

            del_from_playlist(service, playlist_id, expired_items, prog_bar)

        elif utils.history:
            utils.history.info('No expired videos in "%s"', playlist_name)


def cleanup_ended_streams(
    service: pyt.Client, playlist_config: dict[str, PlaylistConfig], prog_bar: bool = True
) -> None:
    """Remove ended streams from playlists with cleanup_on_end=True.

    For each playlist with 'cleanup_on_end' configured:
        1. Fetch all items from the playlist.
        2. Check each video's current liveBroadcastContent status.
        3. Delete items where stream has ended (status is 'none').

    Args:
        service: A Python YouTube Client.
        playlist_config: Dictionary of PlaylistConfig instances.
            Each playlist may have cleanup_on_end configured.
        prog_bar: Whether to use tqdm progress bar.
    """
    for playlist_cfg in playlist_config.values():
        if not playlist_cfg.cleanup_on_end:
            continue

        playlist_id = playlist_cfg.id
        playlist_name = playlist_cfg.name

        if utils.history:
            utils.history.info('Checking ended streams for playlist "%s"', playlist_name)

        all_items = _fetch_stream_playlist_items(service, playlist_id, playlist_name)

        if not all_items:
            if utils.history:
                utils.history.info('No videos in "%s"', playlist_name)
            continue

        ended_items = _find_ended_streams(service, all_items)

        if ended_items:
            if utils.history:
                utils.history.info('Removing %d ended stream(s) from "%s"', len(ended_items), playlist_name)
            del_from_playlist(service, playlist_id, ended_items, prog_bar)

        elif utils.history:
            utils.history.info('No ended streams in "%s"', playlist_name)
