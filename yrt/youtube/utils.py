"""Utility functions and shared state for YouTube operations."""

# Standard library
import datetime as dt
import re
from typing import Any

# Third-party
import pyyoutube as pyt  # type: ignore[import-untyped]
import requests
import tzlocal

# Local
from .. import config
from .. import file_utils
from .. import paths
from ..constants import (
    TRANSIENT_ERRORS,
    PERMANENT_ERRORS,
    QUOTA_ERRORS,
    ISO_DATE_FORMAT,
    LOG_DATE_FORMAT,
)
from ..exceptions import APIError

# Re-export for backward compatibility
__all__ = [
    'TRANSIENT_ERRORS',
    'PERMANENT_ERRORS',
    'QUOTA_ERRORS',
    'ISO_DATE_FORMAT',
    'is_shorts',
]


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
        return dt.datetime.strptime(d_str, LOG_DATE_FORMAT)

    except (FileNotFoundError, IndexError):
        # On first run or corrupted file, default to 24 hours ago (daily workflow)
        return dt.datetime.now(tz=tzlocal.get_localzone()) - dt.timedelta(days=1)


# Module-level state (calculated at import time)
ADD_ON = file_utils.load_json(str(paths.ADD_ON_JSON))
NOW = dt.datetime.now(tz=tzlocal.get_localzone())
LAST_EXE = last_exe_date()

# Logger placeholder - will be set by __init__.py
history = None  # type: ignore[assignment]


def set_logger(logger: Any) -> None:
    """Set the shared logger instance.

    Args:
        logger: Logger instance to use for this module.
    """
    global history
    history = logger


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
        if history:
            history.warning('Failed to check shorts status for video %s: %s', video_id, str(error))
        return False  # Default to non-short on error


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
                if log and history:
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
