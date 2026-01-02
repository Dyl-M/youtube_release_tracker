"""Main process for YouTube Release Tracker."""

# Standard library
import logging
import os
import re
import sys

# Third-party
import github
import pandas as pd

# Local
from . import config
from . import file_utils
from . import paths
from . import youtube
from .exceptions import YouTubeTrackerError, GitHubError

# System

try:
    exe_mode = sys.argv[1]

except IndexError:
    exe_mode = 'local'


def _get_env_variables() -> tuple[str, str]:
    """Get and validate environment variables for GitHub Actions mode.

    :return: Tuple of (github_repo, PAT) values
    :raises ConfigurationError: If required environment variables are missing/empty in 'action' mode
    """
    from .exceptions import ConfigurationError

    try:
        repo = os.environ['GITHUB_REPOSITORY']
        pat = os.environ['PAT']

        # Validate that the values are not empty
        if not repo or not pat:
            raise ValueError("Environment variables are empty")

        return repo, pat

    except (KeyError, ValueError) as er:
        if exe_mode == 'action':
            missing_var = str(er).replace("'", "") if isinstance(er, KeyError) else "GITHUB_REPOSITORY or PAT"
            raise ConfigurationError(
                f"Required environment variable {missing_var} not set or empty. "
                f"Please configure GitHub repository secrets."
            )
        # Fall back to local mode defaults
        return 'Dyl-M/auto_youtube_playlist', 'PAT'


# Environment
github_repo, PAT = _get_env_variables()

# Load configuration files with validation
pocket_tube = file_utils.load_json(
    str(paths.POCKET_TUBE_JSON),
    required_keys=['MUSIQUE', 'APPRENTISSAGE', 'DIVERTISSEMENT', 'GAMING']
)

playlists = file_utils.load_json(
    str(paths.PLAYLISTS_JSON),
    required_keys=['release', 'banger', 're_listening', 'legacy',
                   'apprentissage', 'divertissement_gaming', 'asmr',
                   'music_lives', 'regular_streams']
)

add_on_data = file_utils.load_json(
    str(paths.ADD_ON_JSON),
    required_keys=['favorites']
)

# Extract configuration values
favorites = add_on_data['favorites'].values()

# YouTube Channels list
music = pocket_tube['MUSIQUE']
other_raw = (pocket_tube['APPRENTISSAGE'] + pocket_tube['DIVERTISSEMENT'] +
             pocket_tube['GAMING'] + pocket_tube.get('ASMR', []))
other = list(set(other_raw))
all_channels = list(set(music + other))

# YouTube playlists
release: str = playlists['release']['id']
banger: str = playlists['banger']['id']
re_listening: str = playlists['re_listening']['id']
legacy: str = playlists['legacy']['id']
music_lives: str = playlists['music_lives']['id']
regular_streams: str = playlists['regular_streams']['id']

# Category priority order and playlist mapping (for non-music channels)
CATEGORY_PRIORITY: list[str] = ['APPRENTISSAGE', 'DIVERTISSEMENT', 'GAMING', 'ASMR']

CATEGORY_PLAYLISTS: dict[str, str] = {
    'APPRENTISSAGE': playlists['apprentissage']['id'],
    'DIVERTISSEMENT': playlists['divertissement_gaming']['id'],
    'GAMING': playlists['divertissement_gaming']['id'],
    'ASMR': playlists['asmr']['id'],
}

category_channels = {
    'APPRENTISSAGE': set(pocket_tube['APPRENTISSAGE']),
    'DIVERTISSEMENT': set(pocket_tube['DIVERTISSEMENT']),
    'GAMING': set(pocket_tube['GAMING']),
    'ASMR': set(pocket_tube.get('ASMR', [])),
}

# Historical Data - create if doesn't exist
if os.path.exists(paths.STATS_CSV):
    histo_data = pd.read_csv(paths.STATS_CSV, encoding='utf-8')

else:
    print("INFO: stats.csv not found. Creating new empty DataFrame.")
    # Create empty DataFrame with correct schema
    columns = ['video_id', 'channel_id', 'release_date', 'status', 'is_shorts', 'duration', 'views_w1', 'views_w4',
               'views_w12', 'views_w24', 'likes_w1', 'likes_w4', 'likes_w12', 'likes_w24', 'comments_w1', 'comments_w4',
               'comments_w12', 'comments_w24', 'channel_name', 'video_title']
    histo_data = pd.DataFrame(columns=columns)


# Functions


def copy_last_exe_log() -> None:
    """Copy the last execution logging from the main history file."""
    with open(paths.HISTORY_LOG, 'r', encoding='utf8') as history_file:
        history = history_file.read()

    last_exe = re.findall(r".*?Process started\.", history)[-1]
    last_exe_idx = history.rfind(last_exe)
    last_exe_log = history[last_exe_idx:]

    with open(paths.LAST_EXE_LOG, 'w', encoding='utf8') as last_exe_file:
        last_exe_file.write(last_exe_log)


def dest_playlist(channel_id: str, is_shorts: bool, v_duration: int,
                  live_status: str = 'none', max_duration: int | None = None) -> str:
    """Return destination playlist for addition based on channel category and video properties.

    Routing logic:
    1. Upcoming streams -> route to stream playlists (music_lives or regular_streams)
    2. Shorts are always excluded (return 'shorts')
    3. Non-music channels route to category playlists by priority:
       APPRENTISSAGE > DIVERTISSEMENT/GAMING > ASMR
    4. Music channels:
       - Long videos (>threshold) from dual-category channels -> their non-music category playlist
       - Long videos (>threshold) from music-only channels -> 'none' (skipped)
       - Favorites -> Banger Radar
       - Others -> Release Radar

    :param channel_id: YouTube channel ID
    :param is_shorts: boolean indicating whether the video is a YouTube Short
    :param v_duration: YouTube video duration in seconds
    :param live_status: YouTube live broadcast content status ('none', 'upcoming', 'live')
    :param max_duration: duration threshold in minutes (uses config.LONG_VIDEO_THRESHOLD_MINUTES by default)
    :return: appropriate YouTube playlist ID or special string ('shorts', 'none')
    """
    if max_duration is None:
        max_duration = config.LONG_VIDEO_THRESHOLD_MINUTES

    # Upcoming streams -> route to stream playlists
    if live_status == 'upcoming':
        if channel_id in music:
            return music_lives
        return regular_streams

    if is_shorts:
        return 'shorts'

    is_music_channel = channel_id in music
    is_long_video = v_duration > max_duration * 60

    # Determine non-music category (if any) using priority order
    non_music_category = None
    for category in CATEGORY_PRIORITY:
        if channel_id in category_channels.get(category, set()):
            non_music_category = category
            break

    # Non-music channels -> route to category playlist
    if not is_music_channel:
        if non_music_category:
            return CATEGORY_PLAYLISTS[non_music_category]
        # Channel not in any known category (should not happen normally)
        return 'none'

    # Music channel with long video
    if is_long_video:
        # Dual-category channel: route to non-music category playlist
        if non_music_category:
            return CATEGORY_PLAYLISTS[non_music_category]
        # Music-only channel: skip long videos
        return 'none'

    # Short music videos from favorites -> Banger Radar
    if channel_id in favorites:
        return banger

    # Regular short music videos -> Release Radar
    return release


def update_repo_secrets(secret_name: str, new_value: str, logger: logging.Logger | None = None) -> None:
    """Update a GitHub repository Secret value
    :param secret_name: GH repository Secret name
    :param new_value: new value for the selected Secret
    :param logger: object for logging
    """
    repo = github.Github(auth=github.Auth.Token(PAT)).get_repo(github_repo)
    try:
        repo.create_secret(secret_name, new_value)
        if logger:
            logger.info("Repository Secret '%s' updated successfully.", secret_name)
        else:
            print(f"Repository Secret '{secret_name}' updated successfully.")

    except (github.GithubException, ValueError) as error:
        if logger:
            logger.error("Failed to update Repository Secret '%s' : %s", secret_name, error)

        else:
            print(f"Failed to update secret {secret_name}. Error: {error}")

        raise GitHubError(f"Failed to update Repository Secret '{secret_name}': {error}")


def main(historical_data: pd.DataFrame) -> None:
    """Main process execution.
    :param historical_data: Historical data DataFrame with video statistics.
    """
    # Create loggers
    history_main = logging.Logger(name='history_main', level=0)

    # Create file handlers
    history_main_file = logging.FileHandler(filename=paths.HISTORY_LOG)  # mode='a'

    # Create formatter
    formatter_main = logging.Formatter(fmt='%(asctime)s [%(levelname)s] - %(message)s', datefmt='%Y-%m-%d %H:%M:%S%z')

    # Set file handlers' level
    history_main_file.setLevel(logging.DEBUG)

    # Assign file handlers and formatter to loggers
    history_main_file.setFormatter(formatter_main)
    history_main.addHandler(history_main_file)

    # Start
    history_main.info('Process started.')

    if exe_mode == 'local':  # YouTube service creation
        youtube_oauth, creds_b64 = youtube.create_service_local(), None  # YouTube service in local mode
        prog_bar = True  # Display progress bar

    else:
        # YouTube service with GitHub workflow and Credentials
        youtube_oauth, creds_b64 = youtube.create_service_workflow()
        prog_bar = False  # Do not display the progress bar

    # Add missing videos due to quota exceeded on previous run
    youtube.add_api_fail(service=youtube_oauth, prog_bar=prog_bar)

    # Search for new videos to add
    history_main.info('Iterative research for %s YouTube channels.', len(all_channels))
    new_videos = youtube.iter_channels(youtube_oauth, all_channels, prog_bar=prog_bar)

    if not new_videos:
        history_main.info('No addition to perform.')

        # Get stats for already retrieved videos
        for week_delta in config.STATS_WEEK_DELTAS:
            historical_data = youtube.weekly_stats(
                service=youtube_oauth,
                histo_data=historical_data,
                week_delta=week_delta
            )

        # Store
        historical_data.drop_duplicates(inplace=True)
        historical_data.sort_values(['release_date', 'video_id'], inplace=True)
        historical_data.to_csv(paths.STATS_CSV, encoding='utf-8', index=False)

    else:
        # Add statistics about the videos for selection
        history_main.info('Add statistics for %s video(s).', len(new_videos))
        new_data = youtube.add_stats(service=youtube_oauth, video_list=new_videos)

        # Filter out upcoming streams from stats storage (don't track stats for scheduled content)
        upcoming_mask = new_data['live_status'] == 'upcoming'
        if upcoming_mask.any():
            history_main.info('Filtered %d upcoming stream(s) from stats tracking.', upcoming_mask.sum())

        # Prepare data for storing (excluding upcoming streams)
        to_keep = ['video_id', 'channel_id', 'release_date', 'status', 'is_shorts', 'duration', 'channel_name',
                   'video_title']

        stats_list = ['views_w1', 'views_w4', 'views_w12', 'views_w24', 'likes_w1', 'likes_w4', 'likes_w12',
                      'likes_w24', 'comments_w1', 'comments_w4', 'comments_w12', 'comments_w24']

        stored = new_data[~upcoming_mask][to_keep]
        stored.loc[:, stats_list] = [pd.NA] * len(stats_list)  # type: ignore[assignment]
        stored = stored[to_keep[:-2] + stats_list + to_keep[-2:]]

        # Get stats for already retrieved videos
        for week_delta in config.STATS_WEEK_DELTAS:
            historical_data = youtube.weekly_stats(
                service=youtube_oauth,
                histo_data=historical_data,
                week_delta=week_delta
            )

        # Sort and store (drop all-NA columns before concat to avoid FutureWarning)
        dfs_to_concat = [df.dropna(axis=1, how='all') for df in [historical_data, stored] if not df.empty]
        stored = pd.concat(dfs_to_concat).sort_values(['release_date', 'video_id']).drop_duplicates()
        stored.to_csv(paths.STATS_CSV, encoding='utf-8', index=False)

        # Define destination playlist (use source_channel_id to handle YouTube's auto-generated artist channels)
        new_data['dest_playlist'] = new_data.apply(lambda row: dest_playlist(row.source_channel_id,
                                                                             row.is_shorts,
                                                                             row.duration,
                                                                             row.live_status), axis=1)

        # Reformat
        to_add = new_data.groupby('dest_playlist')['video_id'].apply(list).to_dict()

        # Selection by playlist
        add_banger = to_add.get(banger, [])
        add_release = to_add.get(release, [])

        # Category playlists
        add_apprentissage = to_add.get(playlists['apprentissage']['id'], [])
        add_divert_gaming = to_add.get(playlists['divertissement_gaming']['id'], [])
        add_asmr = to_add.get(playlists['asmr']['id'], [])

        # Stream playlists
        add_music_lives = to_add.get(music_lives, [])
        add_regular_streams = to_add.get(regular_streams, [])

        # Addition by priority (Favorites > Music releases > Category videos)
        if add_banger:
            history_main.info('Addition to "Banger Radar": %s video(s).', len(add_banger))
            youtube.add_to_playlist(youtube_oauth, banger, add_banger, prog_bar=prog_bar)

        if add_release:
            history_main.info('Addition to "Release Radar": %s video(s).', len(add_release))
            youtube.add_to_playlist(youtube_oauth, release, add_release, prog_bar=prog_bar)

        if add_apprentissage:
            history_main.info('Addition to "Educational content": %s video(s).', len(add_apprentissage))
            youtube.add_to_playlist(youtube_oauth, playlists['apprentissage']['id'],
                                    add_apprentissage, prog_bar=prog_bar)

        if add_divert_gaming:
            history_main.info('Addition to "Entertainment & Gaming": %s video(s).', len(add_divert_gaming))
            youtube.add_to_playlist(youtube_oauth, playlists['divertissement_gaming']['id'],
                                    add_divert_gaming, prog_bar=prog_bar)

        if add_asmr:
            history_main.info('Addition to "ASMR & Relaxation": %s video(s).', len(add_asmr))
            youtube.add_to_playlist(youtube_oauth, playlists['asmr']['id'],
                                    add_asmr, prog_bar=prog_bar)

        # Stream playlists
        if add_music_lives:
            history_main.info('Addition to "Music Lives": %s video(s).', len(add_music_lives))
            youtube.add_to_playlist(
                youtube_oauth,
                music_lives,
                add_music_lives,
                prog_bar=prog_bar
            )

        if add_regular_streams:
            history_main.info('Addition to "My streams": %s video(s).', len(add_regular_streams))
            youtube.add_to_playlist(
                youtube_oauth,
                regular_streams,
                add_regular_streams,
                prog_bar=prog_bar
            )

    # Fill the Release Radar playlist (uses config.RELEASE_RADAR_TARGET by default)
    youtube.fill_release_radar(
        youtube_oauth,
        release,
        re_listening,
        legacy,
        prog_bar=prog_bar
    )

    # Cleanup expired videos from category playlists
    youtube.cleanup_expired_videos(youtube_oauth, playlists, prog_bar=prog_bar)

    # Cleanup ended streams from stream playlists
    youtube.cleanup_ended_streams(youtube_oauth, playlists, prog_bar=prog_bar)

    if exe_mode == 'local':  # Credentials in base64 update - Local option
        youtube.encode_key(json_path=str(paths.CREDENTIALS_JSON))
        youtube.encode_key(json_path=str(paths.OAUTH_JSON))

    else:  # Credentials in base64 update - Remote option
        if creds_b64 is not None:
            update_repo_secrets(secret_name='CREDS_B64', new_value=creds_b64, logger=history_main)

    history_main.info('Process ended.')  # End
    copy_last_exe_log()  # Copy what happened during process execution to the associated file.


if __name__ == '__main__':
    # Create a basic logger for top-level exception handling
    top_level_logger = logging.Logger(name='top_level', level=0)
    top_level_handler = logging.FileHandler(filename=paths.HISTORY_LOG)
    top_level_handler.setFormatter(
        logging.Formatter(fmt='%(asctime)s [%(levelname)s] - %(message)s', datefmt='%Y-%m-%d %H:%M:%S%z')
    )
    top_level_logger.addHandler(top_level_handler)

    try:
        main(histo_data)

    except YouTubeTrackerError as e:
        # Handle all custom exceptions (ConfigurationError, APIError, CredentialsError, etc.)
        top_level_logger.critical('Fatal error: %s', e)
        sys.exit(1)
