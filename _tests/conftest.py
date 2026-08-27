"""Pytest configuration and shared fixtures for YouTube Release Tracker tests."""

# Standard library
import datetime as dt
import json
import os
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

# Third-party
import pytest
import requests
from pyyoutube.error import PyYouTubeException
from tzlocal import get_localzone

# Disable logging BEFORE importing yrt modules to prevent log file creation
os.environ['YRT_NO_LOGGING'] = '1'

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
        'is_shorts': False,
    }


@pytest.fixture
def sample_playlist_item():
    """Sample playlist item from YouTube API."""
    return {
        'contentDetails': {'videoId': 'dQw4w9WgXcQ', 'videoPublishedAt': '2024-01-15T12:00:00Z'},
        'snippet': {
            'title': 'Test Video Title',
            'channelId': 'UCuAXFkgsw1L7xaCfnd5JJOw',
            'channelTitle': 'Test Channel',
        },
    }


@pytest.fixture
def sample_video_stats():
    """Sample video statistics from YouTube API."""
    return {
        'id': 'dQw4w9WgXcQ',
        'statistics': {'viewCount': '1000000', 'likeCount': '50000', 'commentCount': '1000'},
        'contentDetails': {'duration': 'PT3M30S'},
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
        'GAMING': ['UCchannel5'],
    }


@pytest.fixture
def sample_playlists_data():
    """Sample playlists.json configuration."""
    return {'banger_radar': 'PLbanger123', 'release_radar': 'PLrelease456', 'watch_later': 'PLwatch789'}


@pytest.fixture
def sample_addon_data():
    """Sample add-on.json configuration."""
    return {'favorites': ['UCchannel1'], 'playlistNotFoundPass': ['UCchannel6'], 'toPass': ['UCchannel7']}


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


@pytest.fixture
def api_error():
    """Factory building a real PyYouTubeException from a JSON error fixture in _tests/fixtures/."""

    def _build(fixture_name):
        """Wrap the fixture body in a Response-shaped mock and raise it through the library's own parser.

        Mock(spec=requests.Response) passes the library's isinstance() check, so .status_code and .message are
        filled exactly as they would be for a real API error.
        """
        body = json.loads((FIXTURES_DIR / fixture_name).read_text(encoding='utf-8'))
        response = Mock(spec=requests.Response)
        response.status_code = body['error']['code']
        response.json.return_value = body
        return PyYouTubeException(response)

    return _build


@pytest.fixture
def no_sleep():
    """Patch the retry layer's sleep so transient paths run instantly; yields the mock for call assertions."""
    with patch('yrt.youtube.retry.time.sleep') as mock_sleep:
        yield mock_sleep


@pytest.fixture
def quota_tracker():
    """Install a small, deterministic QuotaTracker as the process-wide default and return it."""
    from yrt.youtube import quota

    tracker = quota.QuotaTracker(budget=100, daily_quota=1000)
    quota.set_tracker(tracker)
    return tracker


@pytest.fixture
def history_mock(monkeypatch):
    """Replace the shared youtube logger with a MagicMock to assert on log calls."""
    from yrt.youtube import utils

    mock_logger = MagicMock()
    monkeypatch.setattr(utils, 'history', mock_logger)
    return mock_logger


@pytest.fixture
def exec_context(tmp_path):
    """A daily, workflow-mode ExecutionContext with a January 2024 window and log files under tmp_path."""
    from yrt.constants import EXE_MODE_ACTION, JOB_DAILY
    from yrt.context import ExecutionContext

    return ExecutionContext(
        job=JOB_DAILY,
        exe_mode=EXE_MODE_ACTION,
        now=dt.datetime(2024, 2, 1, tzinfo=dt.UTC),
        last_exe=dt.datetime(2024, 1, 1, tzinfo=dt.UTC),
        history_path=tmp_path / 'history.log',
        last_exe_path=tmp_path / 'last_exe.log',
    )


@pytest.fixture
def add_on_config():
    """An AddOnConfig with empty lists (nothing skipped, nothing whitelisted)."""
    from yrt.models import AddOnConfig

    return AddOnConfig(favorites={})


@pytest.fixture
def log_lines():
    """Factory reading a log file as a list of message parts (without timestamps)."""

    def _read(path):
        """Return the message part of every line of a log file."""
        return [line.split(' - ', 1)[1] for line in path.read_text(encoding='utf-8').splitlines()]

    return _read


@pytest.fixture
def session_factory(exec_context):
    """Factory building a runtime.Session with a mock service and a logger on the context's history file."""
    from yrt import runtime
    from yrt.constants import PROCESS_START_MARKER
    from yrt.logging_utils import create_file_logger

    def _build(*, creds_b64=None, target=None, mark_started=False):
        """Build the session; mark_started writes the start marker as bootstrap() would."""
        logger = create_file_logger('history_main', exec_context.history_path, respect_no_logging=False)
        if mark_started:
            logger.info(PROCESS_START_MARKER)
        return runtime.Session(service=MagicMock(), creds_b64=creds_b64, github=target, logger=logger)

    return _build


@pytest.fixture(autouse=True)
def _reset_quota_tracker():
    """Drop the process-wide quota tracker after each test so tests never share spend."""
    yield
    from yrt.youtube import quota

    quota.reset_tracker()


@pytest.fixture(autouse=True)
def _restore_youtube_logger():
    """Put back the shared youtube logger after each test (bootstrap() rebinds it to the job's history file)."""
    from yrt.youtube import utils

    original = utils.history
    yield
    utils.set_logger(original)


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
    extended_allowed = [*original_allowed, temp_dir]

    # Patch the ALLOWED_DIRS
    monkeypatch.setattr(file_utils, 'ALLOWED_DIRS', extended_allowed)

    # Cleanup happens automatically via monkeypatch
