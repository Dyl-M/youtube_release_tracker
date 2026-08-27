"""Daily job of YouTube Release Tracker: subscriptions -> playlists, statistics and cleanups.

Importing this module has no side effect; `python -m yrt.main [local|action]` runs the job through yrt.runtime.
"""

# Standard library
import datetime as dt
import logging
import sys
from collections.abc import Sequence

# Third-party
import pandas as pd

# Local
from . import config, paths, runtime, youtube
from .constants import JOB_DAILY, LIVE_STATUS_UPCOMING
from .context import ExecutionContext
from .models import PlaylistConfig, VideoData, to_dict_list
from .router import create_router_from_config, dest_playlist, set_default_router

# stats.csv columns, in file order: identity, then the weekly statistics, then the display names
STATS_COLUMNS: tuple[str, ...] = (
    'video_id',
    'channel_id',
    'release_date',
    'status',
    'is_shorts',
    'duration',
    'views_w1',
    'views_w4',
    'views_w12',
    'views_w24',
    'likes_w1',
    'likes_w4',
    'likes_w12',
    'likes_w24',
    'comments_w1',
    'comments_w4',
    'comments_w12',
    'comments_w24',
    'channel_name',
    'video_title',
)
STATS_WEEKLY: tuple[str, ...] = STATS_COLUMNS[6:18]  # filled by weekly_stats() over the following weeks
STATS_KEEP: tuple[str, ...] = STATS_COLUMNS[:6] + STATS_COLUMNS[18:]  # known when a video is discovered

# Playlist additions: (playlists.json key, log name), in insertion order
PLAYLIST_ADDITIONS: tuple[tuple[str, str], ...] = (
    ('banger', 'Banger Radar'),
    ('release', 'Release Radar'),
    ('apprentissage', 'Educational content'),
    ('divertissement_gaming', 'Entertainment & Gaming'),
    ('asmr', 'ASMR & Relaxation'),
    ('music_lives', 'Music Lives'),
    ('regular_streams', 'My streams'),
)


def _load_historical_data(logger: logging.Logger) -> pd.DataFrame:
    """Load stats.csv, or start an empty one with the right schema.

    Args:
        logger: Job logger.

    Returns:
        Historical data with video statistics.
    """
    if paths.STATS_CSV.exists():
        return pd.read_csv(paths.STATS_CSV, encoding='utf-8')

    logger.info('stats.csv not found. Creating new empty DataFrame.')
    return pd.DataFrame(columns=list(STATS_COLUMNS))


def _pending_videos() -> list[VideoData]:
    """Return the videos parked for the daily job by the frequent job.

    The queue lives in the 'pending' lists of playlists.json; nothing writes it yet, so this is the merge point for
    the port plan's Phase 5 and returns an empty list for now.

    Returns:
        Videos to add and track, as if they had just been discovered.
    """
    return []


def _update_historical_stats(
    service: youtube.pyt.Client, historical_data: pd.DataFrame, ctx: ExecutionContext
) -> pd.DataFrame:
    """Collect weekly stats for videos in historical data.

    Args:
        service: YouTube API client.
        historical_data: DataFrame with video statistics.
        ctx: Execution context; the run's start time (in UTC) is the reference date of the week deltas.

    Returns:
        Updated DataFrame with collected stats.
    """
    ref_date = ctx.now.astimezone(dt.UTC)
    for week_delta in config.STATS_WEEK_DELTAS:
        historical_data = youtube.weekly_stats(
            service=service, histo_data=historical_data, week_delta=week_delta, ref_date=ref_date
        )
    return historical_data


def _store_stats(historical_data: pd.DataFrame) -> None:
    """Write the historical data back to stats.csv, sorted and de-duplicated.

    Args:
        historical_data: DataFrame with video statistics.
    """
    historical_data.drop_duplicates(inplace=True)
    historical_data.sort_values(['release_date', 'video_id'], inplace=True)
    historical_data.to_csv(paths.STATS_CSV, encoding='utf-8', index=False)


def _store_new_videos(historical_data: pd.DataFrame, new_data: pd.DataFrame, upcoming_mask: pd.Series) -> None:
    """Append the newly discovered videos to stats.csv with empty weekly statistics.

    Args:
        historical_data: DataFrame with video statistics.
        new_data: Newly discovered videos with their current statistics.
        upcoming_mask: Rows of new_data that are scheduled streams (not tracked until they go live).
    """
    stored = new_data[~upcoming_mask][list(STATS_KEEP)]
    stored.loc[:, list(STATS_WEEKLY)] = [pd.NA] * len(STATS_WEEKLY)
    stored = stored[list(STATS_COLUMNS)]

    # Sort and store (drop all-NA columns before concat to avoid FutureWarning)
    dfs_to_concat = [df.dropna(axis=1, how='all') for df in [historical_data, stored] if not df.empty]
    stored = pd.concat(dfs_to_concat).sort_values(['release_date', 'video_id']).drop_duplicates()
    stored.to_csv(paths.STATS_CSV, encoding='utf-8', index=False)


def _add_videos_to_playlists(
    service: youtube.pyt.Client,
    playlists: dict[str, PlaylistConfig],
    to_add: dict[str, list[str]],
    logger: logging.Logger,
    prog_bar: bool,
) -> None:
    """Add videos to their destination playlists.

    Args:
        service: YouTube API client.
        playlists: Playlist definitions by key.
        to_add: Dictionary mapping playlist IDs to lists of video IDs.
        logger: Job logger.
        prog_bar: Whether to display progress bar.
    """
    for key, log_name in PLAYLIST_ADDITIONS:
        playlist_id = playlists[key].id
        videos = to_add.get(playlist_id, [])
        if videos:
            logger.info('Addition to "%s": %s video(s).', log_name, len(videos))
            youtube.add_to_playlist(service, playlist_id, videos, prog_bar=prog_bar)


def run_daily(ctx: ExecutionContext, session: runtime.Session) -> None:
    """The daily job: replay failures, discover uploads, update statistics, route and add, fill and clean up.

    Args:
        ctx: Execution context of the run.
        session: Session opened by runtime.bootstrap().
    """
    cfg = runtime.load_config()
    set_default_router(create_router_from_config(cfg.pocket_tube, cfg.playlists, cfg.add_on))

    service, logger, prog_bar = session.service, session.logger, ctx.prog_bar
    historical_data = _load_historical_data(logger)

    # Add missing videos due to quota exceeded on previous run
    youtube.add_api_fail(service=service, prog_bar=prog_bar)

    # Search for new videos to add, plus the ones parked by the frequent job
    all_channels = cfg.all_channels
    logger.info('Iterative research for %s YouTube channels.', len(all_channels))
    new_videos = youtube.iter_channels(service, all_channels, ctx, cfg.add_on, prog_bar=prog_bar)
    pending = _pending_videos()

    # Update historical stats (common to both branches)
    historical_data = _update_historical_stats(service, historical_data, ctx)

    if not new_videos and not pending:
        logger.info('No addition to perform.')
        _store_stats(historical_data)

    else:
        # Add statistics about the videos for selection (pending videos already carry theirs)
        logger.info('Add statistics for %s video(s).', len(new_videos) + len(pending))
        new_data = youtube.add_stats(service=service, playlist_items=new_videos) if new_videos else pd.DataFrame()
        if pending:
            new_data = pd.concat([new_data, pd.DataFrame(to_dict_list(pending))], ignore_index=True)

        # Filter out upcoming streams from stats storage (don't track stats for scheduled content)
        upcoming_mask = new_data['live_status'] == LIVE_STATUS_UPCOMING
        if upcoming_mask.any():
            logger.info('Filtered %d upcoming stream(s) from stats tracking.', upcoming_mask.sum())

        _store_new_videos(historical_data, new_data, upcoming_mask)

        # Define destination playlist (use source_channel_id to handle YouTube's auto-generated artist channels)
        new_data['dest_playlist'] = new_data.apply(
            lambda row: dest_playlist(row.source_channel_id, row.is_shorts, row.duration, row.live_status), axis=1
        )

        # Add videos to playlists
        destinations = new_data['dest_playlist'].unique().tolist()  # plain strings, one list of IDs per playlist
        to_add = {
            destination: new_data.loc[new_data['dest_playlist'] == destination, 'video_id'].tolist()
            for destination in destinations
        }
        _add_videos_to_playlists(service, cfg.playlists, to_add, logger, prog_bar)

    # Fill the Release Radar playlist (uses config.RELEASE_RADAR_TARGET by default)
    youtube.fill_release_radar(
        service,
        cfg.playlists['release'].id,
        cfg.playlists['re_listening'].id,
        cfg.playlists['legacy'].id,
        ctx,
        prog_bar=prog_bar,
    )

    # Cleanup expired videos from category playlists, then ended streams from stream playlists
    youtube.cleanup_expired_videos(service, cfg.playlists, ctx, prog_bar=prog_bar)
    youtube.cleanup_ended_streams(service, cfg.playlists, prog_bar=prog_bar)


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point of the daily job.

    Args:
        argv: Command-line arguments without the program name (defaults to sys.argv[1:]).

    Returns:
        Process exit code (0 on success, 1 on a handled fatal error).
    """
    exe_mode = runtime.parse_exe_mode(argv, prog='python -m yrt.main')
    return runtime.run_job(JOB_DAILY, exe_mode, run_daily)


if __name__ == '__main__':
    sys.exit(main())
