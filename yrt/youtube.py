"""YouTube API interactions and web scraping methods."""

# Standard library
import ast
import base64
import datetime as dt
import itertools
import json
import math
import os
import random
import re
import time
from typing import Any

# Third-party
import isodate  # type: ignore[import-untyped]
import pandas as pd
import pyyoutube as pyt  # type: ignore[import-untyped]
import requests
import tqdm  # type: ignore[import-untyped]
import tzlocal
from google.auth.exceptions import RefreshError
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow  # type: ignore[import-untyped]

# Local
from . import config
from . import file_utils
from . import paths
from .exceptions import CredentialsError, YouTubeServiceError, APIError, FileAccessError
from .logging_utils import create_file_logger

# Options

pd.set_option('display.max_columns', None)  # pd.set_option('display.max_rows', None)

# Error categorization for API retry logic (normalized to lowercase for comparison)
TRANSIENT_ERRORS = {'serviceunavailable', 'backenderror', 'internalerror'}
PERMANENT_ERRORS = {'videonotfound', 'forbidden', 'playlistoperationunsupported', 'duplicate'}
QUOTA_ERRORS = {'quotaexceeded'}

# Date format for YouTube API responses
ISO_DATE_FORMAT = '%Y-%m-%dT%H:%M:%S%z'


def last_exe_date() -> dt.datetime:
    """Get the last execution datetime from a log file.

    Returns:
        Last execution date, or 24 hours ago if log is missing/empty.
    """
    try:
        with open(paths.LAST_EXE_LOG, 'r', encoding='utf8') as log_file:
            lines = log_file.readlines()
            if not lines:
                # Empty file - default to 24 hours ago (daily workflow)
                return dt.datetime.now(tz=tzlocal.get_localzone()) - dt.timedelta(days=1)
            first_log = lines[0]

        match = re.search(r'(\d{4}(-\d{2}){2})\s(\d{2}:?){3}.[\d:]+', first_log)
        if match is None:
            raise ValueError(f'Could not parse date from log line: {first_log}')

        d_str = match.group()
        return dt.datetime.strptime(d_str, '%Y-%m-%d %H:%M:%S%z')

    except (FileNotFoundError, IndexError):
        # On first run or corrupted file, default to 24 hours ago (daily workflow)
        return dt.datetime.now(tz=tzlocal.get_localzone()) - dt.timedelta(days=1)


ADD_ON = file_utils.load_json(str(paths.ADD_ON_JSON))

NOW = dt.datetime.now(tz=tzlocal.get_localzone())
LAST_EXE = last_exe_date()

# Create logger (only add file handler if not in standalone mode)
history = create_file_logger('history', paths.HISTORY_LOG)


# Functions


def encode_key(json_path: str, export_dir: str | None = None, export_name: str | None = None) -> None:
    """Encode a JSON authentication file to base64.

    Args:
        json_path: File path to authentication JSON file.
        export_dir: Export directory.
        export_name: Export file name.

    Raises:
        FileAccessError: If the file path is invalid or the file does not exist.
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


def create_service_local(log: bool = True) -> pyt.Client:
    """Create a GCP service for YouTube API V3.

    Mostly inspired by this: https://learndataanalysis.org/google-py-file-source-code/

    Args:
        log: Whether to apply logging or not.

    Returns:
        A Google API service object build with 'googleapiclient.discovery.build'.

    Raises:
        YouTubeServiceError: If the service creation fails.
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


def create_service_workflow() -> tuple[pyt.Client, str]:
    """Create a GCP service for YouTube API V3, for usage in GitHub Actions workflow.

    Returns:
        Tuple of (service, creds_b64) where service is a Google API service object.

    Raises:
        CredentialsError: If credentials are missing or cannot be refreshed.
        YouTubeServiceError: If the service creation fails.
    """

    def import_env_var(var_name: str) -> dict[str, Any]:
        """Import environment variable and perform base64 decoding.

        Args:
            var_name: Environment variable name.

        Returns:
            Decoded value as a dictionary.

        Raises:
            CredentialsError: If the environment variable is not found.
        """
        v_b64 = os.environ.get(var_name)  # Get environment variable
        if v_b64 is None:
            raise CredentialsError(f'Environment variable {var_name} not found')
        v_str = base64.urlsafe_b64decode(v_b64).decode(encoding='utf8')  # Decode
        value = ast.literal_eval(v_str)  # Eval
        return value  # type: ignore[no-any-return]

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
        # creds_b64 is guaranteed to be str at this point (import_env_var raises if missing)
        assert creds_b64 is not None
        return service, creds_b64

    except (pyt.error.PyYouTubeException, ValueError, AttributeError) as error:
        history.critical('(%s) %s', error, instance_fail_message)
        raise YouTubeServiceError(f'{instance_fail_message}: {error}')


def _parse_playlist_item(item: Any, date_format: str) -> dict[str, Any] | None:
    """Parse a playlist item into a dict, returns None if no release date.

    Args:
        item: A playlist item from YouTube API response.
        date_format: Date format string for parsing.

    Returns:
        Parsed item dict or None if no release date.
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


def _handle_playlist_error(
        error: pyt.error.PyYouTubeException,
        playlist_id: str,
        add_on: dict[str, Any] | None = None
) -> bool:
    """Handle playlist API errors. Raises APIError for fatal errors.

    Args:
        error: The PyYouTubeException that was raised.
        playlist_id: The playlist ID that caused the error.
        add_on: Configuration dict containing playlistNotFoundPass list. Defaults to global ADD_ON.

    Returns:
        True if should break loop, False otherwise.

    Raises:
        APIError: For unrecognized API errors.
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


def _filter_items_by_date_range(
        p_items: list[dict[str, Any]],
        latest_d: dt.datetime,
        oldest_d: dt.datetime | None = None,
        day_ago: int | None = None
) -> list[dict[str, Any]]:
    """Filter videos on a date range.

    Args:
        p_items: Playlist items as a list.
        latest_d: The latest reference date.
        oldest_d: Latest execution date.
        day_ago: Day difference with a reference date, delimits items' collection field.

    Returns:
        Filtered items.
    """
    if oldest_d:
        return [item for item in p_items if oldest_d < item['release_date'] < latest_d]
    if day_ago:
        date_delta = latest_d - dt.timedelta(days=day_ago)
        return [item for item in p_items if date_delta < item['release_date'] < latest_d]
    return p_items


def get_playlist_items(
        service: pyt.Client,
        playlist_id: str,
        day_ago: int | None = None,
        latest_d: dt.datetime = NOW
) -> list[dict[str, Any]]:
    """Get the videos in a YouTube playlist.

    Args:
        service: A Python YouTube Client.
        playlist_id: A YouTube playlist ID.
        day_ago: Day difference with a reference date, delimits items' collection field.
        latest_d: The latest reference date.

    Returns:
        Playlist items (videos) as a list.
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
                max_results=config.API_BATCH_SIZE,
                pageToken=next_page_token
            )

            # Parse items, filtering out those without release date
            p_items += [parsed for item in request.items
                        if (parsed := _parse_playlist_item(item, ISO_DATE_FORMAT)) is not None]
            p_items = _filter_items_by_date_range(p_items, latest_d, oldest_d=oldest_d, day_ago=day_ago)

            next_page_token = request.nextPageToken

            # No need for more requests (the playlist must be ordered chronologically!)
            if len(p_items) <= config.API_BATCH_SIZE or next_page_token is None:
                break

        except pyt.error.PyYouTubeException as error:
            if _handle_playlist_error(error, playlist_id):
                break

    return p_items


def get_videos(service: pyt.Client, videos_list: list[str]) -> list[Any]:
    """Get information from YouTube videos.

    Args:
        service: A Python YouTube Client.
        videos_list: List of YouTube video IDs.

    Returns:
        Request results.
    """
    return service.videos.list(  # type: ignore[no-any-return]
        part=['snippet', 'contentDetails', 'statistics', 'status'],
        video_id=videos_list,
        max_results=config.API_BATCH_SIZE
    ).items


def get_subs(service: pyt.Client, channel_list: list[str]) -> list[dict[str, Any]]:
    """Get the number of subscribers for several YouTube channels.

    Args:
        service: A Python YouTube Client.
        channel_list: List of YouTube channel IDs.

    Returns:
        Playlist items (channels' information) as a list.
    """
    ch_filter = [channel_id for channel_id in channel_list if channel_id is not None]

    # Split task in chunks to request on a maximum of API_BATCH_SIZE channels at each iteration.
    batch_size = config.API_BATCH_SIZE
    channels_chunks = [ch_filter[i:i + min(batch_size, len(ch_filter))] for i in range(0, len(ch_filter), batch_size)]
    raw_chunk = []

    for chunk in channels_chunks:
        req = service.channels.list(part=['statistics'], channel_id=chunk, max_results=config.API_BATCH_SIZE).items
        raw_chunk += req

    items = [{'channel_id': item.id, 'subscribers': item.statistics.subscriberCount} for item in raw_chunk]

    return items


def check_if_live(service: pyt.Client, videos_list: list[str]) -> list[dict[str, Any]]:
    """Get broadcast status with YouTube video IDs.

    Args:
        service: A Python YouTube Client.
        videos_list: List of YouTube video IDs.

    Returns:
        Playlist items (videos) as a list.

    Raises:
        APIError: If API error occurs while checking live status.
    """
    items = []

    # Split tasks in chunks to request a maximum of API_BATCH_SIZE videos at each iteration.
    batch_size = config.API_BATCH_SIZE
    videos_chunks = [videos_list[i:i + min(batch_size, len(videos_list))]
                     for i in range(0, len(videos_list), batch_size)]

    for chunk in videos_chunks:
        try:
            request = get_videos(service=service, videos_list=chunk)

            # Keep necessary data
            items += [{'video_id': video.id, 'live_status': video.snippet.liveBroadcastContent} for video in request]

        except pyt.error.PyYouTubeException as api_error:
            history.error(api_error.message)
            raise APIError(f'API error while checking live status: {api_error.message}')

    return items


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


def iter_channels(
        service: pyt.Client,
        channels: list[str],
        day_ago: int | None = None,
        latest_d: dt.datetime = NOW,
        prog_bar: bool = True
) -> list[dict[str, Any]]:
    """Apply 'get_playlist_items' for a collection of YouTube playlists.

    Args:
        service: A Python YouTube Client.
        channels: List of YouTube channel IDs.
        day_ago: Day difference with a reference date, delimits items' collection field.
        latest_d: The latest reference date.
        prog_bar: Whether to use tqdm progress bar.

    Returns:
        Videos retrieved in playlists, each with source_channel_id added.
    """
    # Create pairs of (channel_id, playlist_id) to track source channel
    channel_playlist_pairs = [(ch_id, f'UU{ch_id[2:]}') for ch_id in channels if ch_id not in ADD_ON['toPass']]

    def get_items_with_source(channel_id: str, playlist_id: str) -> list[dict[str, Any]]:
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
                if error_reason_normalized in TRANSIENT_ERRORS and attempt < config.MAX_RETRIES - 1:
                    # Calculate exponential backoff with equal jitter to prevent thundering herd
                    delay = min(config.MAX_BACKOFF, int(config.BASE_DELAY * math.exp(attempt)))
                    wait_time = delay / 2 + random.uniform(0, delay / 2)
                    history.warning('Transient error (%s) for video %s, retrying in %.2fs (attempt %s/%s)',
                                    error_reason, video_id, wait_time, attempt + 1, config.MAX_RETRIES)
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


def del_from_playlist(
        service: pyt.Client,
        playlist_id: str,
        items_list: list[dict[str, Any]],
        prog_bar: bool = True
) -> None:
    """Delete videos inside a YouTube playlist.

    Args:
        service: A Python YouTube Client.
        playlist_id: A YouTube playlist ID.
        items_list: List of YouTube playlist items [{"item_id": ..., "video_id": ...}].
        prog_bar: Whether to use tqdm progress bar.
    """
    if prog_bar:
        del_iterator = tqdm.tqdm(items_list, desc=f'Deleting videos from the playlist ({playlist_id})')

    else:
        del_iterator = items_list

    for item in del_iterator:
        try:
            service.playlistItems.delete(playlist_item_id=item['item_id'])

        except pyt.error.PyYouTubeException as http_error:
            history.warning('Deletion Request Failure: (%s) - %s', item['video_id'], http_error.message)


def sort_db(service: pyt.Client, log: bool = True) -> None:
    """Sort and save the PocketTube database file.

    Args:
        service: A Python YouTube Client.
        log: Whether to apply logging or not.
    """

    def get_channels(_service: pyt.Client, _channel_list: list[str]) -> list[str]:
        """Get YouTube channels basic information.

        Args:
            _service: A YouTube service build with 'googleapiclient.discovery'.
            _channel_list: List of YouTube channel IDs.

        Returns:
            A list of channel IDs sorted alphabetically by channel name.

        Raises:
            APIError: If API error occurs while sorting database.
        """
        information = []

        # Split task in chunks to request on a maximum of API_BATCH_SIZE channels at each iteration.
        batch_size = config.API_BATCH_SIZE
        channels_chunks = [_channel_list[i:i + min(batch_size, len(_channel_list))]
                           for i in range(0, len(_channel_list), batch_size)]

        for chunk in channels_chunks:
            try:
                # Request channels
                request = _service.channels.list(part=['snippet'], channel_id=chunk,
                                                 max_results=config.API_BATCH_SIZE).items

                # Extract upload playlists, channel names and their ID.
                information += [{'title': an_item.snippet.title, 'id': an_item.id} for an_item in request]

            except pyt.error.PyYouTubeException as api_error:
                if log:
                    history.error(api_error.message)
                raise APIError(f'API error while sorting database: {api_error.message}')

        # Sort channels' name by alphabetical order
        information = sorted(information, key=lambda dic: dic['title'].lower())
        ids_only = [info['id'] for info in information]  # Get channel IDs only

        return ids_only

    channels_db = file_utils.load_json(str(paths.POCKET_TUBE_JSON))

    categories = [db_keys for db_keys in channels_db.keys() if 'ysc' not in db_keys]  # Get PT categories
    db_sorted = {category: get_channels(_service=service, _channel_list=channels_db[category])
                 for category in categories}

    for category in categories:  # Rewrite categories in the dict object associated with the PT JSON file
        channels_db[category] = db_sorted[category]

    file_utils.save_json(str(paths.POCKET_TUBE_JSON), channels_db)


def is_shorts(video_id: str) -> bool:
    """Check if a YouTube video is a short or not.

    Args:
        video_id: YouTube video ID.

    Returns:
        True if the video is short, False otherwise. Returns False on network errors.
    """
    try:
        response = requests.head(
            f'https://www.youtube.com/shorts/{video_id}',
            timeout=config.NETWORK_TIMEOUT,
            allow_redirects=False
        )
        return response.status_code == 200

    except Exception as error:
        history.warning('Failed to check shorts status for video %s: %s', video_id, str(error))
        return False  # Default to non-short on error


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
        history.info('No change to apply on historical data for following delta: %s week(s)', week_delta)

    # Apply the type Int64 for each feature (necessary for export)
    w_features = [col for col in histo_data.columns if '_w' in col]
    for feature in w_features:
        histo_data[[feature]] = histo_data[[feature]].astype('Int64')

    return histo_data


def get_items_count(service: pyt.Client, playlist_ids: list) -> tuple:
    """Get the number of videos in YouTube Playlists.

    Args:
        service: A Python YouTube Client.
        playlist_ids: List of YouTube playlist IDs.

    Returns:
        Number of videos by playlist (ordered).
    """
    playlists = service.playlists.list(part=['contentDetails'], playlist_id=playlist_ids).items
    return tuple(pl.contentDetails.itemCount for pl in playlists)


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
            history.warning('API quota exceeded.')
        else:
            history.warning('Unknown error: %s', error.message)
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

    history.info('%s addition(s) from %s playlist.', len(videos), source_name)
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
        history.info('No addition necessary for Release Radar')
        return

    # Calculate proportional allocation from each source
    to_re_listen_count, legacy_count = get_items_count(service, [re_listening_id, legacy_id])
    n_add_rel, n_add_leg = _calculate_allocation(n_add, to_re_listen_count, legacy_count)

    # Fetch and format videos from both playlists
    week_ago = NOW - dt.timedelta(weeks=config.RELISTENING_AGE_WEEKS)

    to_re_listen_items = service.playlistItems.list(
        part=['snippet', 'contentDetails'],
        playlist_id=re_listening_id,
        max_results=lmt
    ).items
    to_re_listen_raw = [{'video_id': item.contentDetails.videoId,
                         'add_date': dt.datetime.strptime(item.snippet.publishedAt, ISO_DATE_FORMAT),
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


def cleanup_expired_videos(service: pyt.Client, playlist_config: dict[str, Any], prog_bar: bool = True) -> None:
    """Remove expired videos from playlists with retention rules.

    For each playlist with 'retention_days' configured:
        1. Fetch all items from the playlist.
        2. Filter items where snippet.publishedAt < (NOW - retention_days).
        3. Delete expired items using del_from_playlist().

    Args:
        service: A Python YouTube Client.
        playlist_config: Dictionary of playlist configurations from playlists.json.
            Each playlist entry may have 'retention_days' key.
        prog_bar: Whether to use tqdm progress bar.
    """
    for playlist_cfg in playlist_config.values():
        # Skip playlists without retention rules
        if 'retention_days' not in playlist_cfg:
            continue

        playlist_id = playlist_cfg['id']
        retention_days = playlist_cfg['retention_days']
        playlist_name = playlist_cfg['name']
        cutoff_date = NOW - dt.timedelta(days=retention_days)

        history.info(
            'Checking retention for playlist "%s" (retention: %d days)',
            playlist_name,
            retention_days
        )

        # Fetch all items with pagination
        expired_items = []
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


def _fetch_stream_playlist_items(service: pyt.Client, playlist_id: str, playlist_name: str) -> list[dict[str, Any]]:
    """Fetch all items from a stream playlist with pagination.

    Args:
        service: A Python YouTube Client.
        playlist_id: The playlist ID to fetch items from.
        playlist_name: The playlist name for logging.

    Returns:
        List of items with item_id and video_id.
    """
    all_items: list[dict[str, Any]] = []
    next_page_token = None

    while True:
        try:
            response = service.playlistItems.list(
                parts=['snippet', 'contentDetails'],
                playlist_id=playlist_id,
                count=config.API_BATCH_SIZE,
                page_token=next_page_token
            )

            all_items.extend({'item_id': item.id, 'video_id': item.contentDetails.videoId}
                             for item in response.items)

            next_page_token = response.nextPageToken
            if not next_page_token:
                break

        except pyt.error.PyYouTubeException as error:
            if error.status_code == 403:
                history.warning('API quota exceeded while checking streams for %s', playlist_name)
            else:
                history.warning('Error fetching items from %s: %s', playlist_name, error.message)
            break

    return all_items


def _find_ended_streams(service: pyt.Client, all_items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Find streams that have ended by checking their live status.

    Args:
        service: A Python YouTube Client.
        all_items: List of playlist items with item_id and video_id.

    Returns:
        List of items where the stream has ended.
    """
    video_ids = [item['video_id'] for item in all_items]
    video_id_to_item = {item['video_id']: item for item in all_items}
    ended_items: list[dict[str, Any]] = []

    # Batch video status checks
    batch_size = config.API_BATCH_SIZE
    for i in range(0, len(video_ids), batch_size):
        chunk = video_ids[i:i + batch_size]
        try:
            videos_response = get_videos(service=service, videos_list=chunk)
            for video in videos_response:
                if video.snippet.liveBroadcastContent == 'none' and video.id in video_id_to_item:
                    ended_items.append(video_id_to_item[video.id])

        except pyt.error.PyYouTubeException as error:
            history.warning('Error checking stream status: %s', error.message)

    return ended_items


def cleanup_ended_streams(service: pyt.Client, playlist_config: dict[str, Any], prog_bar: bool = True) -> None:
    """Remove ended streams from playlists with cleanup_on_end=True.

    For each playlist with 'cleanup_on_end' configured:
        1. Fetch all items from the playlist.
        2. Check each video's current liveBroadcastContent status.
        3. Delete items where stream has ended (status is 'none').

    Args:
        service: A Python YouTube Client.
        playlist_config: Dictionary of playlist configurations from playlists.json.
            Each playlist entry may have 'cleanup_on_end' key.
        prog_bar: Whether to use tqdm progress bar.
    """
    for playlist_cfg in playlist_config.values():
        if not playlist_cfg.get('cleanup_on_end', False):
            continue

        playlist_id = playlist_cfg['id']
        playlist_name = playlist_cfg['name']

        history.info('Checking ended streams for playlist "%s"', playlist_name)

        all_items = _fetch_stream_playlist_items(service, playlist_id, playlist_name)

        if not all_items:
            history.info('No videos in "%s"', playlist_name)
            continue

        ended_items = _find_ended_streams(service, all_items)

        if ended_items:
            history.info('Removing %d ended stream(s) from "%s"', len(ended_items), playlist_name)
            del_from_playlist(service, playlist_id, ended_items, prog_bar)

        else:
            history.info('No ended streams in "%s"', playlist_name)


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
            history.info('%s addition(s) to %s playlist from previous API failure.',
                         len(videos_to_retry), info['name'])
            api_failure[p_id]['failure'] = []  # Clear before retry so add_to_playlist can re-add failures
            file_utils.save_json(str(paths.API_FAILURE_JSON), api_failure)  # Save cleared state

            # Failed videos get re-added here
            add_to_playlist(service, p_id, videos_to_retry, prog_bar=prog_bar)
            addition += 1

    if addition > 0:
        history.info('Video recovery from previous API failure(s) complete.')
