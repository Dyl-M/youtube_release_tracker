# -*- coding: utf-8 -*-

import datetime as dt
import json
import pytest

from pathlib import Path
from tzlocal import get_localzone
from unittest.mock import Mock, MagicMock

"""Pytest configuration and shared fixtures for YouTube Release Tracker tests."""

# Test data directory
FIXTURES_DIR = Path(__file__).parent / 'fixtures'


@pytest.fixture
def sample_video_id():
    """Sample YouTube video ID."""
    return 'dQw4w9WgXcQ'


@pytest.fixture
def sample_channel_id():
    """Sample YouTube channel ID."""
    return 'UCuAXFkgsw1L7xaCfnd5JJOw'


@pytest.fixture
def sample_playlist_id():
    """Sample YouTube playlist ID."""
    return 'PLOMUdQFdS-XOI8OIWV_Gx-SRhlCS9PKLn'


@pytest.fixture
def sample_datetime():
    """Sample datetime with timezone."""
    return dt.datetime(2024, 1, 15, 12, 0, 0, tzinfo=get_localzone())


@pytest.fixture
def sample_video_data():
    """Sample video metadata."""
    return {
        'video_id': 'dQw4w9WgXcQ',
        'title': 'Test Video Title',
        'channel_id': 'UCuAXFkgsw1L7xaCfnd5JJOw',
        'channel_title': 'Test Channel',
        'published_at': '2024-01-15T12:00:00Z',
        'duration': 'PT3M30S',  # 3 minutes 30 seconds
        'is_shorts': False
    }


@pytest.fixture
def sample_playlist_item():
    """Sample playlist item from YouTube API."""
    return {
        'contentDetails': {
            'videoId': 'dQw4w9WgXcQ',
            'videoPublishedAt': '2024-01-15T12:00:00Z'
        },
        'snippet': {
            'title': 'Test Video Title',
            'channelId': 'UCuAXFkgsw1L7xaCfnd5JJOw',
            'channelTitle': 'Test Channel'
        }
    }


@pytest.fixture
def sample_video_stats():
    """Sample video statistics from YouTube API."""
    return {
        'id': 'dQw4w9WgXcQ',
        'statistics': {
            'viewCount': '1000000',
            'likeCount': '50000',
            'commentCount': '1000'
        },
        'contentDetails': {
            'duration': 'PT3M30S'
        }
    }


@pytest.fixture
def mock_youtube_client():
    """Mock pyyoutube Client."""
    mock_client = MagicMock()

    # Mock playlistItems
    mock_client.playlistItems = MagicMock()
    mock_client.playlistItems.list = MagicMock()
    mock_client.playlistItems.insert = MagicMock()
    mock_client.playlistItems.delete = MagicMock()

    # Mock videos
    mock_client.videos = MagicMock()
    mock_client.videos.list = MagicMock()

    return mock_client


@pytest.fixture
def sample_pocket_tube_data():
    """Sample pocket_tube.json configuration."""
    return {
        'MUSIQUE': ['UCchannel1', 'UCchannel2'],
        'APPRENTISSAGE': ['UCchannel3'],
        'DIVERTISSEMENT': ['UCchannel4'],
        'GAMING': ['UCchannel5']
    }


@pytest.fixture
def sample_playlists_data():
    """Sample playlists.json configuration."""
    return {
        'banger_radar': 'PLbanger123',
        'release_radar': 'PLrelease456',
        'watch_later': 'PLwatch789'
    }


@pytest.fixture
def sample_addon_data():
    """Sample add-on.json configuration."""
    return {
        'favorites': ['UCchannel1'],
        'playlistNotFoundPass': ['UCchannel6'],
        'toPass': ['UCchannel7']
    }


@pytest.fixture
def temp_json_file(tmp_path):
    """Create a temporary JSON file for testing."""

    def _create_temp_json(data, filename='test.json'):
        """Create a JSON file in the temp directory.

        :param data: Dictionary to write as JSON
        :param filename: Name of the file to create
        :return: Absolute path to the created file
        """
        file_path = tmp_path / filename
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2)
        return str(file_path)

    return _create_temp_json


@pytest.fixture
def mock_requests_response():
    """Mock requests response for is_shorts() testing."""
    mock_response = Mock()
    mock_response.status_code = 200
    return mock_response


@pytest.fixture(autouse=True)
def allow_temp_files(tmp_path, monkeypatch):
    """Automatically allow temp directories in file_utils validation.

    This fixture runs for all tests and adds the pytest temp directory
    to the ALLOWED_DIRS list in file_utils, enabling tests to work with
    temporary files while still testing the validation logic.
    """
    from yrt import file_utils

    # Get current allowed dirs and add temp path
    original_allowed = file_utils.ALLOWED_DIRS.copy()
    temp_dir = str(tmp_path.parent.parent)  # Get pytest's temp root
    extended_allowed = original_allowed + [temp_dir]

    # Patch the ALLOWED_DIRS
    monkeypatch.setattr(file_utils, 'ALLOWED_DIRS', extended_allowed)

    yield

    # Cleanup happens automatically via monkeypatch
