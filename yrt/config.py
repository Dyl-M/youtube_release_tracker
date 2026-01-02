# -*- coding: utf-8 -*-

from __future__ import annotations

import logging

from . import paths
from . import file_utils
from .exceptions import ConfigurationError

"""File Information
@file_name: config.py
@author: Dylan "dyl-m" Monfret
Centralized configuration loading with defaults fallback.
"""

"LOGGER"

# Create logger
logger = logging.Logger(name='config', level=0)

# Create file handler
log_file = logging.FileHandler(filename=paths.HISTORY_LOG)

# Create formatter
formatter = logging.Formatter(fmt='%(asctime)s [%(levelname)s] - %(message)s', datefmt='%Y-%m-%d %H:%M:%S%z')

# Set file handler level
log_file.setLevel(logging.DEBUG)

# Assign file handler and formatter to logger
log_file.setFormatter(formatter)
logger.addHandler(log_file)

"DEFAULTS"

# Default configuration values (used if constants.json is missing or incomplete)
DEFAULTS = {
    'api': {
        'batch_size': 50,
        'max_retries': 3,
        'base_delay_seconds': 1,
        'max_backoff_seconds': 32
    },
    'network': {
        'timeout_seconds': 5
    },
    'playlists': {
        'release_radar_target_size': 40,
        'relistening_age_weeks': 1
    },
    'video': {
        'long_video_threshold_minutes': 10
    },
    'stats': {
        'week_deltas': [1, 4, 12, 24]
    }
}

"FUNCTIONS"


def _deep_merge(defaults: dict, overrides: dict) -> dict:
    """Recursively merge overrides into defaults.

    :param defaults: Base configuration dictionary
    :param overrides: User configuration to merge on top
    :return: Merged configuration dictionary
    """
    result = defaults.copy()
    for key, value in overrides.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def load_constants() -> dict:
    """Load configuration from constants.json with defaults fallback.

    :return: Configuration dictionary (merged with defaults)
    """
    try:
        user_config = file_utils.load_json(str(paths.CONSTANTS_JSON))
        logger.info('Loaded configuration from %s', paths.CONSTANTS_JSON)
        return _deep_merge(DEFAULTS, user_config)

    except ConfigurationError:
        # Config file missing or invalid - use defaults
        logger.warning('Config file not found or invalid, using defaults')
        return DEFAULTS.copy()


"CONFIGURATION"

# Load configuration at module import
_config = load_constants()

# API configuration
API_BATCH_SIZE: int = _config['api']['batch_size']
MAX_RETRIES: int = _config['api']['max_retries']
BASE_DELAY: int = _config['api']['base_delay_seconds']
MAX_BACKOFF: int = _config['api']['max_backoff_seconds']

# Network configuration
NETWORK_TIMEOUT: int = _config['network']['timeout_seconds']

# Playlist configuration
RELEASE_RADAR_TARGET: int = _config['playlists']['release_radar_target_size']
RELISTENING_AGE_WEEKS: int = _config['playlists']['relistening_age_weeks']

# Video configuration
LONG_VIDEO_THRESHOLD_MINUTES: int = _config['video']['long_video_threshold_minutes']

# Statistics configuration
STATS_WEEK_DELTAS: list[int] = _config['stats']['week_deltas']
