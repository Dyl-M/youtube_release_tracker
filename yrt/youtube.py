# -*- coding: utf-8 -*-

from __future__ import annotations

import ast
import base64
import datetime as dt
import isodate  # type: ignore[import-untyped]
import itertools
import json
import logging
import math
import os
import pandas as pd
import pyyoutube as pyt  # type: ignore[import-untyped]
import random
import re
import requests
import time
import tqdm  # type: ignore[import-untyped]
import tzlocal

from google.auth.exceptions import RefreshError
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow  # type: ignore[import-untyped]

from . import file_utils
from . import paths
from .exceptions import CredentialsError, YouTubeServiceError, APIError, FileAccessError

"""File Information
@file_name: youtube.py
@author: Dylan "dyl-m" Monfret
Script containing methods using YouTube API or doing scrapping / GET-requests on youtube.com.
"""

"OPTIONS"

pd.set_option('display.max_columns', None)  # pd.set_option('display.max_rows', None)

"GLOBAL"

# Error categorization for API retry logic (normalized to lowercase for comparison)
TRANSIENT_ERRORS = {'serviceunavailable', 'backenderror', 'internalerror'}
PERMANENT_ERRORS = {'videonotfound', 'forbidden', 'playlistoperationunsupported', 'duplicate'}
QUOTA_ERRORS = {'quotaexceeded'}
MAX_RETRIES = 3
BASE_DELAY = 1  # Base delay in seconds for exponential backoff
MAX_BACKOFF = 32  # Maximum backoff delay in seconds

# Date format for YouTube API responses
ISO_DATE_FORMAT = '%Y-%m-%dT%H:%M:%S%z'


def last_exe_date():
    """Get the last execution datetime from a log file (supposing the first line is containing the right datetime).
    :return date: Last execution date.
    """
    with open(paths.LAST_EXE_LOG, 'r', encoding='utf8') as log_file:
        first_log = log_file.readlines()[0]  # Get first log

    d_str = re.search(r'(\d{4}(-\d{2}){2})\s(\d{2}:?){3}.[\d:]+', first_log).group()  # Extract date
    date = dt.datetime.strptime(d_str, '%Y-%m-%d %H:%M:%S%z')  # Parse to datetime object
    return date


ADD_ON = file_utils.load_json(str(paths.ADD_ON_JSON))

NOW = dt.datetime.now(tz=tzlocal.get_localzone())
LAST_EXE = last_exe_date()

"LOGGERS"

# Create loggers
history = logging.Logger(name='history', level=0)

# Create file handlers
history_file = logging.FileHandler(filename=paths.HISTORY_LOG)  # mode='a'

# Create formatter
formatter = logging.Formatter(fmt='%(asctime)s [%(levelname)s] - %(message)s', datefmt='%Y-%m-%d %H:%M:%S%z')

# Set file handlers' level
history_file.setLevel(logging.DEBUG)

# Assign file handlers and formatter to loggers
history_file.setFormatter(formatter)
history.addHandler(history_file)

"FUNCTIONS"


def encode_key(json_path: str, export_dir: str | None = None, export_name: str | None = None):
    """Encode a JSON authentication file to base64
    :param json_path: file's path to authentication JSON file
    :param export_dir: export directory
    :param export_name: export file name.
    """
    path_split = json_path.split('/')
    file_name = path_split[-1].removesuffix('.json')

    if export_dir is None:
        export_dir = json_path.removesuffix(f'{file_name}.json')

    if export_name is None:
        export_name = f'{file_name}_b64.txt'

    if '_tokens' not in json_path:
        history.critical('FORBIDDEN ACCESS. Invalid file path.')
        raise FileAccessError('FORBIDDEN ACCESS. Invalid file path.')

    if not os.path.exists(json_path):
        history.error('%s file does not exist.', json_path)
        raise FileAccessError(f'{json_path} file does not exist.')

    with open(json_path, 'r', encoding='utf8') as json_file:
        key_dict = json.load(json_file)

    key_str = json.dumps(key_dict).encode('utf-8')
    key_b64 = base64.urlsafe_b64encode(key_str)

    with open(export_dir + export_name, 'wb') as key_file:
        key_file.write(key_b64)


def create_service_local(log: bool = True):
    """Create a GCP service for YouTube API V3.
    Mostly inspired by this: https://learndataanalysis.org/google-py-file-source-code/
    :param log: to apply logging or not
    :return service: a Google API service object build with 'googleapiclient.discovery.build'.
    """
    oauth_file = paths.OAUTH_JSON  # OAUTH 2.0 ID path
    scopes = ['https://www.googleapis.com/auth/youtube', 'https://www.googleapis.com/auth/youtube.force-ssl']
    instance_fail_message = 'Failed to create service instance for YouTube'
    cred = None

    if os.path.exists(paths.CREDENTIALS_JSON):
        cred = Credentials.from_authorized_user_file(paths.CREDENTIALS_JSON)  # Retrieve credentials

    if not cred or not cred.valid:  # Cover outdated or non-existant credentials
        if cred and cred.expired and cred.refresh_token:
            try:
                cred.refresh(Request())

            except RefreshError:
                history.info('Credentials can not be refreshed. New credentials needed.')
                flow = InstalledAppFlow.from_client_secrets_file(oauth_file, scopes)  # Create a Flow from 'oauth_file'
                cred = flow.run_local_server()  # Run the authentication process

        else:
            # Create the authentification Flow from 'oauth_file' and then run the authentication process
            flow = InstalledAppFlow.from_client_secrets_file(oauth_file, scopes)
            cred = flow.run_local_server()

        with open(paths.CREDENTIALS_JSON, 'w') as cred_file:  # Save credentials as a JSON file
            # noinspection PyTypeChecker
            json.dump(ast.literal_eval(cred.to_json()), cred_file, ensure_ascii=False, indent=4)

    try:
        service = pyt.Client(client_id=cred.client_id, client_secret=cred.client_secret, access_token=cred.token)
        if log:
            history.info('YouTube service created successfully.')

        return service

    except (pyt.error.PyYouTubeException, ValueError, AttributeError) as error:
        if log:
            history.critical('(%s) %s', error, instance_fail_message)

        raise YouTubeServiceError(f'{instance_fail_message}: {error}')


def create_service_workflow():
    """Create a GCP service for YouTube API V3, for usage in GitHub Actions workflow
    :return service: a Google's API service object build with 'googleapiclient.discovery.build'.
    """

    def import_env_var(var_name: str):
        """Import variable environment and perform base64 decoding
        :param var_name: environment variable name
        :return value: decoded value
        """
        v_b64 = os.environ.get(var_name)  # Get environment variable
        if v_b64 is None:
            raise CredentialsError(f'Environment variable {var_name} not found')
        v_str = base64.urlsafe_b64decode(v_b64).decode(encoding='utf8')  # Decode
        value = ast.literal_eval(v_str)  # Eval
        return value

    creds_b64 = os.environ.get('CREDS_B64')  # Initiate the Base64 version of the Credentials object
    creds_dict = import_env_var(var_name='CREDS_B64')  # Import pre-registered credentials
    creds = Credentials.from_authorized_user_info(creds_dict)  # Conversion to a suitable object
    instance_fail_message = 'Failed to create service instance for YouTube'

    if not creds.valid:  # Cover outdated credentials
        if creds.expired and creds.refresh_token:
            creds.refresh(Request())  # Refresh token

            # Get refreshed token as JSON-like string
            creds_str = json.dumps(ast.literal_eval(creds.to_json())).encode('utf-8')

            creds_b64 = str(base64.urlsafe_b64encode(creds_str))[2:-1]  # Encode token
            os.environ['CREDS_B64'] = creds_b64  # Update environment variable value
            history.info('API credentials refreshed.')

        else:
            history.critical('ERROR: Unable to refresh credentials. Check Google API OAUTH parameter.')
            raise CredentialsError('Unable to refresh credentials. Check Google API OAUTH parameter.')

    try:
        service = pyt.Client(client_id=creds.client_id, client_secret=creds.client_secret, access_token=creds.token)
        history.info('YouTube service created successfully.')
        return service, creds_b64

    except (pyt.error.PyYouTubeException, ValueError, AttributeError) as error:
        history.critical('(%s) %s', error, instance_fail_message)
        raise YouTubeServiceError(f'{instance_fail_message}: {error}')


def _parse_playlist_item(item, date_format: str):
    """Parse a playlist item into a dict, returns None if no release date.
    :param item: A playlist item from YouTube API response.
    :param date_format: Date format string for parsing.
    :return: Parsed item dict or None if no release date.
    """
    if item.contentDetails.videoPublishedAt is None:
        return None
    return {
        'video_id': item.contentDetails.videoId,
        'video_title': item.snippet.title,
        'item_id': item.id,
        'release_date': dt.datetime.strptime(item.contentDetails.videoPublishedAt, date_format),
        'status': item.status.privacyStatus,
        'channel_id': item.snippet.videoOwnerChannelId,
        'channel_name': item.snippet.videoOwnerChannelTitle
    }


def _handle_playlist_error(error: pyt.error.PyYouTubeException, playlist_id: str, add_on: dict | None = None):
    """Handle playlist API errors. Exits program for fatal errors.
    :param error: The PyYouTubeException that was raised.
    :param playlist_id: The playlist ID that caused the error.
    :param add_on: Configuration dict containing playlistNotFoundPass list. Defaults to global ADD_ON.
    :return: True if should break loop, False otherwise. Exits program for fatal errors.
    """
    if add_on is None:
        add_on = ADD_ON

    if error.status_code == 404:
        channel_id = f'UC{playlist_id[2:]}'
        if channel_id not in add_on['playlistNotFoundPass']:
            history.warning('Playlist not found: %s', playlist_id)
        return True

    history.error('[%s] Unknown error: %s', playlist_id, error.message)
    raise APIError(f'[{playlist_id}] Unknown error: {error.message}')


def _filter_items_by_date_range(p_items: list, latest_d: dt.datetime,
                                oldest_d: dt.datetime | None = None, day_ago: int | None = None):
    """Filter videos on a date range.
    :param p_items: Playlist items as a list.
    :param latest_d: The latest reference date.
    :param oldest_d: Latest execution date.
    :param day_ago: Day difference with a reference date, delimits items' collection field.
    :return: Filtered items.
    """
    if oldest_d:
        return [item for item in p_items if oldest_d < item['release_date'] < latest_d]
    if day_ago:
        date_delta = latest_d - dt.timedelta(days=day_ago)
        return [item for item in p_items if date_delta < item['release_date'] < latest_d]
    return p_items


def get_playlist_items(service: pyt.Client, playlist_id: str, day_ago: int | None = None, latest_d: dt.datetime = NOW):
    """Get the videos in a YouTube playlist.
    :param service: A Python YouTube Client.
    :param playlist_id: A YouTube playlist ID.
    :param day_ago: Day difference with a reference date, delimits items' collection field.
    :param latest_d: The latest reference date.
    :return p_items: Playlist items (videos) as a list.
    """
    p_items = []
    next_page_token = None

    latest_d = latest_d.replace(minute=0, second=0, microsecond=0)
    oldest_d = None if day_ago else LAST_EXE.replace(minute=0, second=0, microsecond=0)

    while True:
        try:
            request = service.playlistItems.list(
                part=['snippet', 'contentDetails', 'status'],
                playlist_id=playlist_id,
                max_results=50,
                pageToken=next_page_token
            )

            # Parse items, filtering out those without release date
            p_items += [parsed for item in request.items
                        if (parsed := _parse_playlist_item(item, ISO_DATE_FORMAT)) is not None]
            p_items = _filter_items_by_date_range(p_items, latest_d, oldest_d=oldest_d, day_ago=day_ago)

            next_page_token = request.nextPageToken

            # No need for more requests (the playlist must be ordered chronologically!)
            if len(p_items) <= 50 or next_page_token is None:
                break

        except pyt.error.PyYouTubeException as error:
            if _handle_playlist_error(error, playlist_id):
                break

    return p_items


def get_videos(service: pyt.Client, videos_list: list):
    """Get information from YouTube videos
    :param service: a Python YouTube Client
    :param videos_list: list of YouTube video IDs
    :return: request results.
    """
    return service.videos.list(part=['snippet', 'contentDetails', 'statistics', 'status'],
                               video_id=videos_list,
                               max_results=50).items


def get_subs(service: pyt.Client, channel_list: list):
    """Get the number of subscribers for several YouTube channels
    :param service: a Python YouTube Client
    :param channel_list: list of YouTube channel IDs
    :return: playlist items (channels' information) as a list.
    """
    ch_filter = [channel_id for channel_id in channel_list if channel_id is not None]

    # Split task in chunks of size 50 to request on a maximum of 50 channels at each iteration.
    channels_chunks = [ch_filter[i:i + min(50, len(ch_filter))] for i in range(0, len(ch_filter), 50)]
    raw_chunk = []

    for chunk in channels_chunks:
        req = service.channels.list(part=['statistics'], channel_id=chunk, max_results=50).items
        raw_chunk += req

    items = [{'channel_id': item.id, 'subscribers': item.statistics.subscriberCount} for item in raw_chunk]

    return items


def check_if_live(service: pyt.Client, videos_list: list):
    """Get broadcast status with YouTube video IDs
    :param service: a Python YouTube Client
    :param videos_list: list of YouTube video IDs
    :return items: playlist items (videos) as a list.
    """
    items = []

    # Split tasks in chunks of size 50 to request a maximum of 50 videos at each iteration.
    videos_chunks = [videos_list[i:i + min(50, len(videos_list))] for i in range(0, len(videos_list), 50)]

    for chunk in videos_chunks:
        try:
            request = get_videos(service=service, videos_list=chunk)

            # Keep necessary data
            items += [{'video_id': video.id, 'live_status': video.snippet.liveBroadcastContent} for video in request]

        except pyt.error.PyYouTubeException as api_error:
            history.error(api_error.message)
            raise APIError(f'API error while checking live status: {api_error.message}')

    return items


def get_stats(service: pyt.Client, videos_list: list, check_shorts: bool = True):
    """Get duration, views and live status of YouTube video with their ID
    :param service: a Python YouTube Client
    :param videos_list: list of YouTube video IDs
    :param check_shorts: whether to check if videos are shorts (skip for historical stats updates)
    :return items: playlist items (videos) as a list.
    """
    items = []

    try:
        videos_ids = [video['video_id'] for video in videos_list]

    except TypeError:
        videos_ids = videos_list

    # Split tasks in chunks of size 50 to request a maximum of 50 videos at each iteration.
    videos_chunks = [videos_ids[i:i + min(50, len(videos_ids))] for i in range(0, len(videos_ids), 50)]

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
                       'is_shorts': is_shorts(video_id=item.id) if check_shorts else None,
                       'live_status': item.snippet.liveBroadcastContent,
                       'latest_status': item.status.privacyStatus} for item in request]

        except pyt.error.PyYouTubeException as api_error:
            history.error(api_error.message)
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


def add_stats(service: pyt.Client, video_list: list):
    """Apply 'get_playlist_items' for a collection of YouTube playlists
    :param service: a Python YouTube Client
    :param video_list: list of videos formatted by iter_channels functions
    :return: dataframe with every information necessary
    """
    video_first_data = pd.DataFrame(video_list)
    additional_data = pd.DataFrame(get_stats(service, video_first_data.video_id.tolist()))
    return video_first_data.merge(additional_data)


def iter_channels(service: pyt.Client, channels: list, day_ago: int | None = None, latest_d: dt.datetime = NOW,
                  prog_bar: bool = True):
    """Apply 'get_playlist_items' for a collection of YouTube playlists.
    :param channels: List of YouTube channel IDs.
    :param service: A Python YouTube Client.
    :param day_ago: Day difference with a reference date, delimits items' collection field.
    :param latest_d: The latest reference date.
    :param prog_bar: To use tqdm progress bar or not.
    :return: Videos retrieved in playlists, each with source_channel_id added.
    """
    # Create pairs of (channel_id, playlist_id) to track source channel
    channel_playlist_pairs = [(ch_id, f'UU{ch_id[2:]}') for ch_id in channels if ch_id not in ADD_ON['toPass']]

    def get_items_with_source(channel_id: str, playlist_id: str):
        """Fetch playlist items and add source_channel_id to each."""
        items = get_playlist_items(service=service, playlist_id=playlist_id, day_ago=day_ago, latest_d=latest_d)
        for item in items:
            item['source_channel_id'] = channel_id
        return items

    if prog_bar:
        item_it = [get_items_with_source(ch_id, pl_id)
                   for ch_id, pl_id in tqdm.tqdm(channel_playlist_pairs, desc='Looking for videos to add')]

    else:
        item_it = [get_items_with_source(ch_id, pl_id) for ch_id, pl_id in channel_playlist_pairs]

    return list(itertools.chain.from_iterable(item_it))


def add_to_playlist(service: pyt.Client, playlist_id: str, videos_list: list, prog_bar: bool = True):
    """Add a list of video to a YouTube playlist
    :param service: a Python YouTube Client
    :param playlist_id: a YouTube playlist ID
    :param videos_list: list of YouTube video IDs
    :param prog_bar: to use tqdm progress bar or not.
    """
    api_failure = file_utils.load_json(str(paths.API_FAILURE_JSON))
    api_fail = False

    if prog_bar:
        add_iterator = tqdm.tqdm(videos_list, desc=f'Adding videos to the playlist ({playlist_id})')
    else:
        add_iterator = videos_list

    for video_id in add_iterator:
        r_body = {'snippet': {'playlistId': playlist_id, 'resourceId': {'kind': 'youtube#video', 'videoId': video_id}}}

        for attempt in range(MAX_RETRIES):
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
                if error_reason_normalized in TRANSIENT_ERRORS and attempt < MAX_RETRIES - 1:
                    # Calculate exponential backoff with equal jitter to prevent thundering herd
                    delay = min(MAX_BACKOFF, int(BASE_DELAY * math.exp(attempt)))
                    wait_time = delay / 2 + random.uniform(0, delay / 2)
                    history.warning('Transient error (%s) for video %s, retrying in %.2fs (attempt %s/%s)',
                                    error_reason, video_id, wait_time, attempt + 1, MAX_RETRIES)
                    time.sleep(wait_time)
                    continue

                # Handle permanent errors - log and skip, don't save for retry
                if error_reason_normalized in PERMANENT_ERRORS:
                    history.warning('Permanent error (%s) for video %s - skipping: %s',
                                    error_reason, video_id, http_error.message)
                    break  # Don't save to api_failure.json

                # Handle quota errors or failed transient retries - save for next day retry
                history.warning('Addition Request Failure: (%s) - %s - %s',
                                video_id, error_reason, http_error.message)
                api_failure[playlist_id]['failure'].append(video_id)
                api_fail = True
                break

    if api_fail:  # Save API failure
        file_utils.save_json(str(paths.API_FAILURE_JSON), api_failure)


def del_from_playlist(service: pyt.Client, playlist_id: str, items_list: list, prog_bar: bool = True):
    """Delete videos inside a YouTube playlist
    :param service: a Python YouTube Client
    :param playlist_id: a YouTube playlist ID
    :param items_list: list of YouTube playlist items [{"item_id": ..., "video_id": ...}]
    :param prog_bar: to use tqdm progress bar or not.
    """
    if prog_bar:
        del_iterator = tqdm.tqdm(items_list, desc=f'Deleting videos from the playlist ({playlist_id})')

    else:
        del_iterator = items_list

    for item in del_iterator:
        try:
            service.playlistItems.delete(playlist_item_id=item['item_id'])

        except pyt.error.PyYouTubeException as http_error:  # skipcq: PYL-W0703
            history.warning('Deletion Request Failure: (%s) - %s', item['video_id'], http_error.message)


def sort_db(service: pyt.Client):
    """Sort and save the PocketTube database file
    :param service: a Python YouTube Client
    """

    def get_channels(_service: pyt.Client, _channel_list: list):
        """Get YouTube channels basic information
        :param _service: a YouTube's service build with 'googleapiclient.discovery'
        :param _channel_list: list of YouTube channel ID
        :return information: a dictionary with channels names, IDs and uploads playlist IDs.
        """
        information = []

        # Split task in chunks of size 50 to request on a maximum of 50 channels at each iteration.
        channels_chunks = [_channel_list[i:i + min(50, len(_channel_list))] for i in range(0, len(_channel_list), 50)]

        for chunk in channels_chunks:
            try:
                # Request channels
                request = _service.channels.list(part=['snippet'], channel_id=chunk, max_results=50).items

                # Extract upload playlists, channel names and their ID.
                information += [{'title': an_item.snippet.title, 'id': an_item.id} for an_item in request]

            except pyt.error.PyYouTubeException as api_error:
                history.error(api_error.message)
                raise APIError(f'API error while sorting database: {api_error.message}')

        # Sort channels' name by alphabetical order
        information = sorted(information, key=lambda dic: dic['title'].lower())
        ids_only = [info['id'] for info in information]  # Get channel IDs only

        return ids_only

    channels_db = file_utils.load_json(str(paths.POCKET_TUBE_JSON))

    categories = [db_keys for db_keys in channels_db.keys() if 'ysc' not in db_keys]  # Get PT categories
    db_sorted = {category: get_channels(_service=service, _channel_list=channels_db[category])
                 for category in categories}  # Get sorted categories

    for category in categories:  # Rewrite categories in the dict object associated with the PT JSON file
        channels_db[category] = db_sorted[category]

    file_utils.save_json(str(paths.POCKET_TUBE_JSON), channels_db)


def is_shorts(video_id: str):
    """Check if a YouTube video is a short or not
    :param video_id: YouTube video ID
    :return: True if the video is short, False otherwise. Returns False on network errors.
    """
    try:
        response = requests.head(
            f'https://www.youtube.com/shorts/{video_id}',
            timeout=5,
            allow_redirects=False
        )
        return response.status_code == 200

    except Exception as error:
        history.warning('Failed to check shorts status for video %s: %s', video_id, str(error))
        return False  # Default to non-short on error


def weekly_stats(service: pyt.Client, histo_data: pd.DataFrame, week_delta: int,
                 ref_date: dt.datetime = dt.datetime.now(dt.timezone.utc)):
    """Add weekly statistics to historical data retrieved from YouTube for each run.
    :param service: A Python YouTube Client.
    :param histo_data: Data with statistics retrieved throughout the weeks.
    :param week_delta: How far we should get stats for videos (1, 4, 13 or 26 weeks).
    :param ref_date: A reference date (midnight UTC by default).
    :return histo_data: Historical data enhanced with new statistics.
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
        history.info('No change to apply on historical data for following delta: %s week(s)', week_delta)

    # Apply the type Int64 for each feature (necessary for export)
    w_features = [col for col in histo_data.columns if '_w' in col]
    for feature in w_features:
        histo_data[[feature]] = histo_data[[feature]].astype('Int64')

    return histo_data


def get_items_count(service: pyt.Client, playlist_ids: list) -> tuple:
    """Get the number of videos in YouTube Playlists
    :param service: a Python YouTube Client
    :param playlist_ids: list of YouTube playlist ID
    :return: Number of videos by playlist (ordered)
    """
    playlists = service.playlists.list(part=['contentDetails'], playlist_id=playlist_ids).items
    return tuple(pl.contentDetails.itemCount for pl in playlists)


def fill_release_radar(service: pyt.Client, target_playlist: str, re_listening_id: str, legacy_id: str, lmt: int = 30,
                       prog_bar: bool = True):
    """Fill the Release Radar playlist with videos from re-listening playlists.
    :param service: A Python YouTube Client.
    :param target_playlist: YouTube playlist ID where videos need to be added.
    :param re_listening_id: YouTube playlist ID for music to re-listen to.
    :param legacy_id: An older YouTube playlist to clear out.
    :param lmt: The addition threshold (30 by default).
    :param prog_bar: To use tqdm progress bar or not.
    """
    week_ago = NOW - dt.timedelta(weeks=1)

    # Compute how many videos are necessary to fill the target playlist
    try:
        n_add = lmt - len(service.playlistItems.list(part=['snippet'],
                                                     max_results=lmt,
                                                     playlist_id=target_playlist).items)
    except pyt.PyYouTubeException as error:
        if error.status_code == 403:
            history.warning('API quota exceeded.')
            n_add = 0

        else:
            history.warning('Unknown error: %s', error.message)
            n_add = 0

    if n_add == 0:  # Release Radar has too much content already
        history.info('No addition necessary for Release Radar')

    else:
        to_re_listen_count, legacy_count = get_items_count(service, [re_listening_id, legacy_id])
        re_listen_ratio = to_re_listen_count / (to_re_listen_count + legacy_count)
        legacy_ratio = legacy_count / (to_re_listen_count + legacy_count)

        if re_listen_ratio < legacy_ratio:
            n_add_rel, n_add_leg = math.ceil(n_add * re_listen_ratio), math.floor(n_add * legacy_ratio)
        else:
            n_add_rel, n_add_leg = math.floor(n_add * re_listen_ratio), math.ceil(n_add * legacy_ratio)

        # Get videos from both playlists
        to_re_listen_items = service.playlistItems.list(part=['snippet', 'contentDetails'],
                                                        playlist_id=re_listening_id,
                                                        max_results=lmt).items

        legacy_items = service.playlistItems.list(part=['contentDetails'], playlist_id=legacy_id, max_results=lmt).items

        # Format list for treatment
        to_re_listen_raw = [{'video_id': item.contentDetails.videoId,
                             'add_date': dt.datetime.strptime(item.snippet.publishedAt, ISO_DATE_FORMAT),
                             'item_id': item.id} for item in to_re_listen_items]

        legacy_raw = [{'video_id': item.contentDetails.videoId, 'item_id': item.id} for item in legacy_items]

        # Filter re-listening: keep videos added at least a week ago
        to_re_listen_fil = [item for item in to_re_listen_raw if item['add_date'] < week_ago]

        # Pre-selection
        addition_rel = to_re_listen_fil[:n_add_rel]
        addition_leg = legacy_raw[:n_add_leg]

        if len(addition_leg) < n_add_leg:  # If not enough content in Legacy playlist
            addition_rel = to_re_listen_fil[:n_add - len(addition_leg)]

        if len(addition_rel) < n_add_rel:  # If not enough content in Re-listening playlist
            addition_leg = legacy_raw[:n_add - len(addition_rel)]

        # Perform updates on playlist
        if addition_rel:  # If any addition from re-listening
            history.info('%s addition(s) from Re-listening playlist.', len(addition_rel))
            add_to_playlist(service, target_playlist, [it['video_id'] for it in addition_rel], prog_bar)
            del_from_playlist(service, re_listening_id, addition_rel, prog_bar)

        if addition_leg:  # If any addition from Legacy
            history.info('%s addition(s) from Legacy playlist.', len(addition_leg))
            add_to_playlist(service, target_playlist, [it['video_id'] for it in addition_leg], prog_bar)
            del_from_playlist(service, legacy_id, addition_leg, prog_bar)


def cleanup_expired_videos(service: pyt.Client, playlist_config: dict, prog_bar: bool = True):
    """Remove expired videos from playlists with retention rules.

    For each playlist with 'retention_days' configured:
    1. Fetch all items from the playlist
    2. Filter items where snippet.publishedAt < (NOW - retention_days)
    3. Delete expired items using del_from_playlist()

    :param service: A Python YouTube Client.
    :param playlist_config: Dictionary of playlist configurations from playlists.json.
                           Each playlist entry may have 'retention_days' key.
    :param prog_bar: To use tqdm progress bar or not.
    """
    for config in playlist_config.values():
        # Skip playlists without retention rules
        if 'retention_days' not in config:
            continue

        playlist_id = config['id']
        retention_days = config['retention_days']
        playlist_name = config['name']
        cutoff_date = NOW - dt.timedelta(days=retention_days)

        history.info('Checking retention for playlist "%s" (retention: %d days)', playlist_name, retention_days)

        # Fetch all items with pagination
        expired_items = []
        next_page_token = None

        while True:
            try:
                response = service.playlistItems.list(
                    part=['snippet', 'contentDetails'],
                    playlist_id=playlist_id,
                    max_results=50,
                    pageToken=next_page_token
                )

                for item in response.items:
                    # snippet.publishedAt is when the video was added to the playlist
                    added_date_str = item.snippet.publishedAt
                    if added_date_str:
                        added_date = dt.datetime.strptime(added_date_str, ISO_DATE_FORMAT)
                        if added_date < cutoff_date:
                            expired_items.append({
                                'item_id': item.id,
                                'video_id': item.contentDetails.videoId
                            })

                next_page_token = response.nextPageToken
                if not next_page_token:
                    break

            except pyt.error.PyYouTubeException as error:
                if error.status_code == 403:
                    history.warning('API quota exceeded while checking retention for %s', playlist_name)
                else:
                    history.warning('Error fetching items from %s: %s', playlist_name, error.message)
                break

        # Delete expired items
        if expired_items:
            history.info('Removing %d expired video(s) from "%s"', len(expired_items), playlist_name)
            del_from_playlist(service, playlist_id, expired_items, prog_bar)
        else:
            history.info('No expired videos in "%s"', playlist_name)


def add_api_fail(service: pyt.Client, prog_bar: bool = True):
    """Add missing videos to a targeted playlist following API failures on a previous run
    :param service: a Python YouTube Client
    :param prog_bar: to use tqdm progress bar or not.
    """
    api_failure = file_utils.load_json(str(paths.API_FAILURE_JSON))
    addition = 0

    for p_id, info in api_failure.items():
        if info['failure']:
            videos_to_retry = info['failure'].copy()  # Copy the list before clearing
            history.info('%s addition(s) to %s playlist from previous API failure.',
                         len(videos_to_retry), info['name'])
            api_failure[p_id]['failure'] = []  # Clear before retry so add_to_playlist can re-add failures
            file_utils.save_json(str(paths.API_FAILURE_JSON), api_failure)  # Save cleared state
            add_to_playlist(service, p_id, videos_to_retry, prog_bar=prog_bar)  # Failed videos get re-added here
            addition += 1

    if addition > 0:
        history.info('Video recovery from previous API failure(s) complete.')


if __name__ == '__main__':
    serv = create_service_local(log=False)
    sort_db(service=serv)
