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
from ..exceptions import APIError
from . import utils
from .api import get_videos


def get_stats(service: pyt.Client, videos_list: list[Any], check_shorts: bool = True) -> list[dict[str, Any]]:
    """Get duration, views and live status of YouTube video with their ID.

    Args:
        service: A Python YouTube Client.
        videos_list: List of YouTube video IDs.
        check_shorts: Whether to check if videos are shorts (skip for historical stats updates).

    Returns:
        Playlist items (videos) as a list.

    Raises:
        APIError: If API error occurs while getting stats.
    """
    items = []

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
            items += [{'video_id': item.id,
                       'views': item.statistics.viewCount,
                       'likes': item.statistics.likeCount,
                       'comments': item.statistics.commentCount,
                       'duration': isodate.parse_duration(getattr(item.contentDetails,
                                                                  'duration', 'PT0S') or 'PT0S').seconds,
                       'is_shorts': utils.is_shorts(video_id=item.id) if check_shorts else None,
                       'live_status': item.snippet.liveBroadcastContent,
                       'latest_status': item.status.privacyStatus} for item in request]

        except pyt.error.PyYouTubeException as api_error:
            if utils.history:
                utils.history.error(api_error.message)
            raise APIError(f'API error while getting stats: {api_error.message}')

    validated = [video['video_id'] for video in items]
    missing = [vid_id for vid_id in videos_list if vid_id not in validated]

    items += [{'video_id': item_id,
               'views': None,
               'likes': None,
               'comments': None,
               'duration': None,
               'is_shorts': None,
               'live_status': None,
               'latest_status': 'deleted'} for item_id in missing]

    return items


def add_stats(service: pyt.Client, video_list: list[dict[str, Any]]) -> pd.DataFrame:
    """Apply 'get_playlist_items' for a collection of YouTube playlists.

    Args:
        service: A Python YouTube Client.
        video_list: List of videos formatted by iter_channels functions.

    Returns:
        DataFrame with every information necessary.
    """
    video_first_data = pd.DataFrame(video_list)
    additional_data = pd.DataFrame(get_stats(service, video_first_data.video_id.tolist()))
    return video_first_data.merge(additional_data)


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
    histo_data['release_date'] = pd.to_datetime(histo_data.release_date)
    date_mask = (histo_data.release_date.dt.date == x_week_ago.date()) & (histo_data[f'views_w{week_delta}'].isnull())
    selection = histo_data[date_mask]
    id_mask = selection.video_id.tolist()

    if not selection.empty:  # If some videos are concerned
        vid_id_list = selection.video_id.tolist()  # Get YouTube videos' ID as a list

        # Apply get_stats and keep only the three necessary features (skip shorts check for historical data)
        to_keep = ['video_id', 'views', 'likes', 'comments', 'latest_status']
        stats = pd.DataFrame(get_stats(service, vid_id_list, check_shorts=False))[to_keep]
        histo_data = histo_data.merge(stats, how='left')  # Merge to previous dataframe

        # Add values to corresponding week delta and remove redondant columns in dataframe
        histo_data.loc[histo_data.video_id.isin(id_mask), [f'views_w{week_delta}']] = histo_data.views
        histo_data.loc[histo_data.video_id.isin(id_mask), [f'likes_w{week_delta}']] = histo_data.likes
        histo_data.loc[histo_data.video_id.isin(id_mask), [f'comments_w{week_delta}']] = histo_data.comments
        histo_data.loc[histo_data.video_id.isin(id_mask), ['status']] = histo_data.latest_status
        histo_data.drop(columns=['views', 'likes', 'comments', 'latest_status'], axis=1, inplace=True)

    else:
        if utils.history:
            utils.history.info('No change to apply on historical data for following delta: %s week(s)', week_delta)

    # Apply the type Int64 for each feature (necessary for export)
    w_features = [col for col in histo_data.columns if '_w' in col]
    for feature in w_features:
        histo_data[[feature]] = histo_data[[feature]].astype('Int64')

    return histo_data
