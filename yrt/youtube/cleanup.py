"""Cleanup functions for YouTube playlists."""

# Standard library
import datetime as dt

# Third-party
import pyyoutube as pyt  # type: ignore[import-untyped]

# Local
from .. import config
from ..constants import LIVE_STATUS_NONE
from ..models import PlaylistConfig, PlaylistItemRef
from . import utils
from .api import get_videos
from .playlist import del_from_playlist


def _fetch_stream_playlist_items(service: pyt.Client, playlist_id: str, playlist_name: str) -> list[PlaylistItemRef]:
    """Fetch all items from a stream playlist with pagination.

    Args:
        service: A Python YouTube Client.
        playlist_id: The playlist ID to fetch items from.
        playlist_name: The playlist name for logging.

    Returns:
        List of PlaylistItemRef instances with item_id and video_id.
    """
    all_items: list[PlaylistItemRef] = []
    next_page_token = None

    while True:
        try:
            response = service.playlistItems.list(
                part=['snippet', 'contentDetails'],
                playlist_id=playlist_id,
                max_results=config.API_BATCH_SIZE,
                pageToken=next_page_token
            )

            all_items.extend(
                PlaylistItemRef(item_id=item.id, video_id=item.contentDetails.videoId)
                for item in response.items
            )

            next_page_token = response.nextPageToken
            if not next_page_token:
                break

        except pyt.error.PyYouTubeException as error:
            if error.status_code == 403:
                if utils.history:
                    utils.history.warning('API quota exceeded while checking streams for %s', playlist_name)
            else:
                if utils.history:
                    utils.history.warning('Error fetching items from %s: %s', playlist_name, error.message)
            break

    return all_items


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
    batch_size = config.API_BATCH_SIZE
    for i in range(0, len(video_ids), batch_size):
        chunk = video_ids[i:i + batch_size]
        try:
            videos_response = get_videos(service=service, videos_list=chunk)
            for video in videos_response:
                if video.snippet.liveBroadcastContent == LIVE_STATUS_NONE and video.id in video_id_to_item:
                    ended_items.append(video_id_to_item[video.id])

        except pyt.error.PyYouTubeException as error:
            if utils.history:
                utils.history.warning('Error checking stream status: %s', error.message)

    return ended_items


def cleanup_expired_videos(
        service: pyt.Client,
        playlist_config: dict[str, PlaylistConfig],
        prog_bar: bool = True
) -> None:
    """Remove expired videos from playlists with retention rules.

    For each playlist with 'retention_days' configured:
        1. Fetch all items from the playlist.
        2. Filter items where snippet.publishedAt < (NOW - retention_days).
        3. Delete expired items using del_from_playlist().

    Args:
        service: A Python YouTube Client.
        playlist_config: Dictionary of PlaylistConfig instances.
            Each playlist may have retention_days configured.
        prog_bar: Whether to use tqdm progress bar.
    """
    for playlist_cfg in playlist_config.values():
        # Skip playlists without retention rules
        if playlist_cfg.retention_days is None:
            continue

        playlist_id = playlist_cfg.id
        retention_days = playlist_cfg.retention_days
        playlist_name = playlist_cfg.name
        cutoff_date = utils.NOW - dt.timedelta(days=retention_days)

        if utils.history:
            utils.history.info(
                'Checking retention for playlist "%s" (retention: %d days)',
                playlist_name,
                retention_days
            )

        # Fetch all items with pagination
        expired_items: list[PlaylistItemRef] = []
        next_page_token = None

        while True:
            try:
                response = service.playlistItems.list(
                    part=['snippet', 'contentDetails'],
                    playlist_id=playlist_id,
                    max_results=config.API_BATCH_SIZE,
                    pageToken=next_page_token
                )

                for item in response.items:
                    # snippet.publishedAt is when the video was added to the playlist
                    added_date_str = item.snippet.publishedAt
                    if added_date_str:
                        added_date = dt.datetime.strptime(added_date_str, utils.ISO_DATE_FORMAT)
                        if added_date < cutoff_date:
                            expired_items.append(
                                PlaylistItemRef(
                                    item_id=item.id,
                                    video_id=item.contentDetails.videoId,
                                    add_date=added_date
                                )
                            )

                next_page_token = response.nextPageToken
                if not next_page_token:
                    break

            except pyt.error.PyYouTubeException as error:
                if error.status_code == 403:
                    if utils.history:
                        utils.history.warning('API quota exceeded while checking retention for %s', playlist_name)
                else:
                    if utils.history:
                        utils.history.warning('Error fetching items from %s: %s', playlist_name, error.message)
                break

        # Delete expired items
        if expired_items:
            if utils.history:
                utils.history.info('Removing %d expired video(s) from "%s"', len(expired_items), playlist_name)
            del_from_playlist(service, playlist_id, expired_items, prog_bar)

        else:
            if utils.history:
                utils.history.info('No expired videos in "%s"', playlist_name)


def cleanup_ended_streams(
        service: pyt.Client,
        playlist_config: dict[str, PlaylistConfig],
        prog_bar: bool = True
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

        else:
            if utils.history:
                utils.history.info('No ended streams in "%s"', playlist_name)
