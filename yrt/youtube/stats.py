"""Statistics functions for YouTube video data."""

# Standard library
import datetime as dt
from typing import Any

# Third-party
import isodate  # type: ignore[import-untyped]
import pandas as pd
import pyyoutube as pyt  # type: ignore[import-untyped]

# Local
from .. import config
from ..constants import STATUS_DELETED
from ..exceptions import APIError
from ..models import PlaylistItem, VideoStats, VideoData, to_dict_list
from . import utils
from .api import get_videos


def get_stats(service: pyt.Client, videos_list: list[Any], check_shorts: bool = True) -> list[VideoStats]:
    """Get duration, views and live status of YouTube video with their ID.

    Args:
        service: A Python YouTube Client.
        videos_list: List of YouTube video IDs.
        check_shorts: Whether to check if videos are shorts (skip for historical stats updates).

    Returns:
        Video statistics as list of VideoStats instances.

    Raises:
        APIError: If API error occurs while getting stats.
    """
    items: list[VideoStats] = []

    try:
        videos_ids = [video['video_id'] for video in videos_list]

    except TypeError:
        videos_ids = videos_list

    # Split tasks in chunks to request a maximum of API_BATCH_SIZE videos at each iteration.
    batch_size = config.API_BATCH_SIZE
    videos_chunks = [videos_ids[i:i + min(batch_size, len(videos_ids))] for i in range(0, len(videos_ids), batch_size)]

    for chunk in videos_chunks:
        try:
            request = get_videos(service=service, videos_list=chunk)

            # Keep necessary data
            items += [
                VideoStats(
                    video_id=item.id,
                    views=item.statistics.viewCount,
                    likes=item.statistics.likeCount,
                    comments=item.statistics.commentCount,
                    duration=isodate.parse_duration(getattr(item.contentDetails, 'duration', 'PT0S') or 'PT0S').seconds,
                    is_shorts=utils.is_shorts(video_id=item.id) if check_shorts else None,
                    live_status=item.snippet.liveBroadcastContent,
                    latest_status=item.status.privacyStatus
                )
                for item in request
            ]

        except pyt.error.PyYouTubeException as api_error:
            if utils.history:
                utils.history.error(api_error.message)
            raise APIError(f'API error while getting stats: {api_error.message}')

    validated = [video.video_id for video in items]
    missing = [vid_id for vid_id in videos_ids if vid_id not in validated]

    items += [
        VideoStats(
            video_id=item_id,
            views=None,
            likes=None,
            comments=None,
            duration=None,
            is_shorts=None,
            live_status=None,
            latest_status=STATUS_DELETED
        )
        for item_id in missing
    ]

    return items


def add_stats(service: pyt.Client, playlist_items: list[PlaylistItem]) -> pd.DataFrame:
    """Add statistics to playlist items and merge into complete video data.

    Args:
        service: A Python YouTube Client.
        playlist_items: List of PlaylistItem instances.

    Returns:
        DataFrame with complete video data.
    """
    # Get video IDs from playlist items
    video_ids = [item.video_id for item in playlist_items]

    # Fetch stats for all videos
    stats_list = get_stats(service, video_ids)

    # Create lookup dict for stats
    stats_by_id = {stat.video_id: stat for stat in stats_list}

    # Merge PlaylistItem + VideoStats into VideoData
    video_data_list = [
        VideoData.from_playlist_item_and_stats(item, stats_by_id[item.video_id])
        for item in playlist_items
    ]

    # Convert to DataFrame
    return pd.DataFrame(to_dict_list(video_data_list))


def weekly_stats(
        service: pyt.Client,
        histo_data: pd.DataFrame,
        week_delta: int,
        ref_date: dt.datetime = dt.datetime.now(dt.timezone.utc)
) -> pd.DataFrame:
    """Add weekly statistics to historical data retrieved from YouTube for each run.

    Args:
        service: A Python YouTube Client.
        histo_data: Data with statistics retrieved throughout the weeks.
        week_delta: How far we should get stats for videos (1, 4, 13 or 26 weeks).
        ref_date: A reference date (midnight UTC by default).

    Returns:
        Historical data enhanced with new statistics.
    """
    # Get the date from "x week ago"
    x_week_ago = ref_date.replace(hour=0, minute=0, second=0, microsecond=0) - dt.timedelta(weeks=week_delta)

    # Filter data with this new reference date
    histo_data['release_date'] = pd.to_datetime(histo_data.release_date, format='ISO8601')
    date_mask = (histo_data.release_date.dt.date == x_week_ago.date()) & (histo_data[f'views_w{week_delta}'].isnull())
    selection = histo_data[date_mask]
    id_mask = selection.video_id.tolist()

    if not selection.empty:  # If some videos are concerned
        vid_id_list = selection.video_id.tolist()  # Get YouTube videos' ID as a list

        # Apply get_stats and keep only the three necessary features (skip shorts check for historical data)
        to_keep = ['video_id', 'views', 'likes', 'comments', 'latest_status']
        stats_list = get_stats(service, vid_id_list, check_shorts=False)
        stats = pd.DataFrame(to_dict_list(stats_list))[to_keep]
        histo_data = histo_data.merge(stats, how='left')  # Merge to previous dataframe

        # Add values to corresponding week delta and remove redondant columns in dataframe
        histo_data.loc[histo_data.video_id.isin(id_mask), [f'views_w{week_delta}']] = histo_data.views
        histo_data.loc[histo_data.video_id.isin(id_mask), [f'likes_w{week_delta}']] = histo_data.likes
        histo_data.loc[histo_data.video_id.isin(id_mask), [f'comments_w{week_delta}']] = histo_data.comments
        histo_data.loc[histo_data.video_id.isin(id_mask), ['status']] = histo_data.latest_status
        histo_data.drop(columns=['views', 'likes', 'comments', 'latest_status'], inplace=True)

    else:
        if utils.history:
            utils.history.info('No change to apply on historical data for following delta: %s week(s)', week_delta)

    # Apply the type Int64 for each feature (necessary for export)
    w_features = [col for col in histo_data.columns if '_w' in col]
    for feature in w_features:
        histo_data[[feature]] = histo_data[[feature]].astype('Int64')

    return histo_data
