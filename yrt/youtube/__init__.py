"""YouTube API interactions and web scraping methods.

This package provides functions for interacting with the YouTube Data API v3,
including authentication, video discovery, statistics collection, and playlist management.
"""

# Third-party
import pandas as pd
import pyyoutube as pyt

# Local
from .. import paths
from ..logging_utils import create_file_logger

# Create shared logger (only add file handler if not in standalone mode)
history = create_file_logger('history', paths.HISTORY_LOG)

# Import submodules after logger is created
from . import utils  # noqa: E402

# Set the logger in utils module
utils.set_logger(history)

# Import all public functions from submodules
from .api import (  # noqa: E402
    check_if_live,
    get_playlist_items,
    get_subs,
    get_videos,
    iter_channels,
)
from .auth import (  # noqa: E402
    create_service_local,
    create_service_workflow,
    encode_key,
)
from .cleanup import (  # noqa: E402
    cleanup_ended_streams,
    cleanup_expired_videos,
)
from .playlist import (  # noqa: E402
    add_api_fail,
    add_to_playlist,
    del_from_playlist,
    fill_release_radar,
)
from .stats import (  # noqa: E402
    add_stats,
    get_stats,
    weekly_stats,
)
from .utils import (  # noqa: E402
    ADD_ON,
    ISO_DATE_FORMAT,
    LAST_EXE,
    # Constants and state
    NOW,
    PERMANENT_ERRORS,
    QUOTA_ERRORS,
    TRANSIENT_ERRORS,
    get_items_count,
    is_shorts,
    last_exe_date,
    sort_db,
)

# Pandas options
pd.set_option('display.max_columns', None)

# Public API
__all__ = [
    # Utils
    'last_exe_date',
    'is_shorts',
    'sort_db',
    'get_items_count',
    'NOW',
    'LAST_EXE',
    'ADD_ON',
    'ISO_DATE_FORMAT',
    'TRANSIENT_ERRORS',
    'PERMANENT_ERRORS',
    'QUOTA_ERRORS',
    # Auth
    'encode_key',
    'create_service_local',
    'create_service_workflow',
    # API
    'get_playlist_items',
    'get_videos',
    'get_subs',
    'check_if_live',
    'iter_channels',
    # Stats
    'get_stats',
    'add_stats',
    'weekly_stats',
    # Playlist
    'add_to_playlist',
    'del_from_playlist',
    'fill_release_radar',
    'add_api_fail',
    # Cleanup
    'cleanup_expired_videos',
    'cleanup_ended_streams',
    # Third-party re-exports (for type hints in main.py)
    'pyt',
]
