# -*- coding: utf-8 -*-

import github
import logging
import os
import pandas as pd
import re
import sys

from . import file_utils
from . import paths
from . import youtube
from .exceptions import YouTubeTrackerError, GitHubError

"""File Information
@file_name: main.py
@author: Dylan "dyl-m" Monfret
Main process.
"""

"ENVIRONMENT"

try:
    github_repo = os.environ['GITHUB_REPOSITORY']
    PAT = os.environ['PAT']

except KeyError:
    github_repo = 'Dyl-M/auto_youtube_playlist'
    PAT = 'PAT'

"SYSTEM"

try:
    exe_mode = sys.argv[1]

except IndexError:
    exe_mode = 'local'

"PARAMETER FILES"

# Load configuration files with validation
pocket_tube = file_utils.load_json(
    str(paths.POCKET_TUBE_JSON),
    required_keys=['MUSIQUE', 'APPRENTISSAGE', 'DIVERTISSEMENT', 'GAMING']
)

playlists = file_utils.load_json(
    str(paths.PLAYLISTS_JSON),
    required_keys=['release', 'banger', 'watch_later', 're_listening', 'legacy']
)

add_on_data = file_utils.load_json(
    str(paths.ADD_ON_JSON),
    required_keys=['favorites']
)

# Extract configuration values
favorites = add_on_data['favorites'].values()

# YouTube Channels list
music = pocket_tube['MUSIQUE']
other_raw = pocket_tube['APPRENTISSAGE'] + pocket_tube['DIVERTISSEMENT'] + pocket_tube['GAMING']
other = list(set(other_raw))
all_channels = list(set(music + other))

# YouTube playlists
release = playlists['release']['id']
banger = playlists['banger']['id']
watch_later = playlists['watch_later']['id']
re_listening = playlists['re_listening']['id']
legacy = playlists['legacy']['id']

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

"FUNCTIONS"


def copy_last_exe_log():
    """Copy the last execution logging from the main history file."""
    with open(paths.HISTORY_LOG, 'r', encoding='utf8') as history_file:
        history = history_file.read()

    last_exe = re.findall(r".*?Process started\.", history)[-1]
    last_exe_idx = history.rfind(last_exe)
    last_exe_log = history[last_exe_idx:]

    with open(paths.LAST_EXE_LOG, 'w', encoding='utf8') as last_exe_file:
        last_exe_file.write(last_exe_log)


def dest_playlist(channel_id: str, is_shorts: bool, v_duration: int, max_duration: int = 10):
    """Return destination playlist for addition
    :param channel_id: YouTube channel ID
    :param is_shorts: boolean indicating whether the video is a YouTube Short or not
    :param v_duration: YouTube video duration in seconds
    :param max_duration: duration threshold in minutes
    :return: appropriate YouTube playlist ID based on video information
    """
    if is_shorts:
        return 'shorts'

    is_music_channel = channel_id in music
    is_long_video = v_duration > max_duration * 60

    # Non-music channels -> Watch Later
    if not is_music_channel:
        return watch_later

    # Long music videos -> Watch Later (if also in other categories) or skip
    if is_long_video:
        return watch_later if channel_id in other else 'none'

    # Short music videos from favorites -> Banger Radar
    if channel_id in favorites:
        return banger

    # Regular short music videos -> Release Radar
    return release


def update_repo_secrets(secret_name: str, new_value: str, logger: logging.Logger = None):
    """Update a GitHub repository Secret value
    :param secret_name: GH repository Secret name
    :param new_value: new value for the selected Secret
    :param logger: object for logging
    """
    repo = github.Github(PAT).get_repo(github_repo)
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
        historical_data = youtube.weekly_stats(service=youtube_oauth, histo_data=historical_data, week_delta=1)
        historical_data = youtube.weekly_stats(service=youtube_oauth, histo_data=historical_data, week_delta=4)
        historical_data = youtube.weekly_stats(service=youtube_oauth, histo_data=historical_data, week_delta=12)
        historical_data = youtube.weekly_stats(service=youtube_oauth, histo_data=historical_data, week_delta=24)

        # Store
        historical_data.drop_duplicates(inplace=True)
        historical_data.sort_values(['release_date', 'video_id'], inplace=True)
        historical_data.to_csv(paths.STATS_CSV, encoding='utf-8', index=False)

    else:
        # Add statistics about the videos for selection
        history_main.info('Add statistics for %s video(s).', len(new_videos))
        new_data = youtube.add_stats(service=youtube_oauth, video_list=new_videos)

        # Prepare data for storing
        to_keep = ['video_id', 'channel_id', 'release_date', 'status', 'is_shorts', 'duration', 'channel_name',
                   'video_title']

        stats_list = ['views_w1', 'views_w4', 'views_w12', 'views_w24', 'likes_w1', 'likes_w4', 'likes_w12',
                      'likes_w24', 'comments_w1', 'comments_w4', 'comments_w12', 'comments_w24']

        stored = new_data[to_keep]
        stored.loc[:, stats_list] = [pd.NA] * len(stats_list)
        stored = stored[to_keep[:-2] + stats_list + to_keep[-2:]]

        # Get stats for already retrieved videos
        historical_data = youtube.weekly_stats(service=youtube_oauth, histo_data=historical_data, week_delta=1)
        historical_data = youtube.weekly_stats(service=youtube_oauth, histo_data=historical_data, week_delta=4)
        historical_data = youtube.weekly_stats(service=youtube_oauth, histo_data=historical_data, week_delta=12)
        historical_data = youtube.weekly_stats(service=youtube_oauth, histo_data=historical_data, week_delta=24)

        # Sort and store
        stored = pd.concat([historical_data, stored]).sort_values(['release_date', 'video_id']).drop_duplicates()
        stored.to_csv(paths.STATS_CSV, encoding='utf-8', index=False)

        # Define destination playlist (use source_channel_id to handle YouTube's auto-generated artist channels)
        new_data['dest_playlist'] = new_data.apply(lambda row: dest_playlist(row.source_channel_id,
                                                                             row.is_shorts,
                                                                             row.duration), axis=1)

        # Reformat
        to_add = new_data.groupby('dest_playlist')['video_id'].apply(list).to_dict()

        # Selection by playlist. An error could happen here!
        add_banger = to_add.get(banger, [])
        add_release = to_add.get(release, [])
        add_wl = to_add.get(watch_later, [])

        # Addition by priority (Favorites > Music releases > Normal videos > Shorts)
        if add_banger:
            history_main.info('Addition to "Banger Radar": %s video(s).', len(add_banger))
            youtube.add_to_playlist(youtube_oauth, banger, add_banger, prog_bar=prog_bar)

        if add_release:
            history_main.info('Addition to "Release Radar": %s video(s).', len(add_release))
            youtube.add_to_playlist(youtube_oauth, release, add_release, prog_bar=prog_bar)

        if add_wl:
            history_main.info('Addition to "Watch Later": %s video(s).', len(add_wl))
            youtube.add_to_playlist(youtube_oauth, watch_later, add_wl, prog_bar=prog_bar)

    # Fill the Release Radar playlist
    youtube.fill_release_radar(youtube_oauth, release, re_listening, legacy, lmt=40, prog_bar=prog_bar)

    if exe_mode == 'local':  # Credentials in base64 update - Local option
        youtube.encode_key(json_path=str(paths.CREDENTIALS_JSON))
        youtube.encode_key(json_path=str(paths.OAUTH_JSON))

    else:  # Credentials in base64 update - Remote option
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
