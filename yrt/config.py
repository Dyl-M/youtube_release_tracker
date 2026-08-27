"""Centralized configuration loading with defaults fallback and validation."""

# Standard library
import copy
from typing import Any

# Local
from . import file_utils, paths
from .exceptions import ConfigurationError
from .logging_utils import create_file_logger

# Create logger (only add file handler if not in standalone mode)
logger = create_file_logger('config', paths.HISTORY_LOG)

# Default configuration values (used if constants.json is missing or incomplete)
DEFAULTS: dict[str, Any] = {
    'api': {
        'batch_size': 50,
        'max_retries': 3,
        'base_delay_seconds': 1,
        'max_backoff_seconds': 32,
        'daily_quota': 10000,
    },
    'network': {'timeout_seconds': 5},
    'quota': {'daily_job_budget': 7000, 'updates_job_budget': 2500},
    'playlists': {'release_radar_target_size': 40, 'relistening_age_weeks': 1},
    'video': {'long_video_threshold_minutes': 10},
    'stats': {'week_deltas': [1, 4, 12, 24]},
}

# Upper bound imposed by the YouTube Data API on maxResults
_API_MAX_BATCH_SIZE = 50


# Functions


def _deep_merge(defaults: dict, overrides: dict) -> dict:
    """Recursively merge overrides into defaults.

    Args:
        defaults: Base configuration dictionary.
        overrides: User configuration to merge on top.

    Returns:
        Merged configuration dictionary.
    """
    result = defaults.copy()
    for key, value in overrides.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def _require_int(config: dict, section: str, key: str, *, minimum: int, maximum: int | None = None) -> int:
    """Fetch an integer setting and check it lies within bounds.

    Args:
        config: Merged configuration dictionary.
        section: Top-level section name (e.g. 'api').
        key: Setting name inside the section.
        minimum: Smallest accepted value (inclusive).
        maximum: Largest accepted value (inclusive), unbounded when None.

    Returns:
        The validated integer.

    Raises:
        ConfigurationError: If the setting is missing, not an integer, or out of bounds.
    """
    file_path = str(paths.CONSTANTS_JSON)

    try:
        value = config[section][key]
    except (KeyError, TypeError) as error:
        raise ConfigurationError(f'Missing configuration key: {section}.{key}', file_path=file_path) from error

    # bool is a subclass of int: reject it explicitly so `true` in JSON is not read as 1
    is_int = isinstance(value, int) and not isinstance(value, bool)
    in_bounds = is_int and value >= minimum and (maximum is None or value <= maximum)

    if not in_bounds:
        bounds = f'>= {minimum}' if maximum is None else f'in [{minimum}, {maximum}]'
        raise ConfigurationError(f'{section}.{key} must be an integer {bounds}, got {value!r}', file_path=file_path)

    return int(value)  # validated above; int() only narrows the type for mypy


def _validate_config(config: dict) -> None:
    """Validate that configuration values are within acceptable ranges.

    Args:
        config: Merged configuration dictionary (defaults + overrides).

    Raises:
        ConfigurationError: On the first invalid setting found.
    """
    _require_int(config, 'api', 'batch_size', minimum=1, maximum=_API_MAX_BATCH_SIZE)
    _require_int(config, 'api', 'max_retries', minimum=0)
    base_delay = _require_int(config, 'api', 'base_delay_seconds', minimum=1)
    _require_int(config, 'api', 'max_backoff_seconds', minimum=base_delay)
    daily_quota = _require_int(config, 'api', 'daily_quota', minimum=1)

    _require_int(config, 'network', 'timeout_seconds', minimum=1)

    _require_int(config, 'quota', 'daily_job_budget', minimum=1, maximum=daily_quota)
    _require_int(config, 'quota', 'updates_job_budget', minimum=1, maximum=daily_quota)

    _require_int(config, 'playlists', 'release_radar_target_size', minimum=1)
    _require_int(config, 'playlists', 'relistening_age_weeks', minimum=1)

    _require_int(config, 'video', 'long_video_threshold_minutes', minimum=1)

    week_deltas = config.get('stats', {}).get('week_deltas')
    valid_deltas = (
        isinstance(week_deltas, list)
        and len(week_deltas) > 0
        and all(isinstance(delta, int) and not isinstance(delta, bool) and delta >= 1 for delta in week_deltas)
    )
    if not valid_deltas:
        raise ConfigurationError(
            f'stats.week_deltas must be a non-empty list of positive integers, got {week_deltas!r}',
            file_path=str(paths.CONSTANTS_JSON),
        )


def load_constants() -> dict:
    """Load configuration from constants.json with defaults fallback, then validate it.

    A missing or malformed file is not an error: defaults are used with a warning. Values that are present but out
    of range are an error, because silently running with defaults would hide an operator mistake.

    Returns:
        Configuration dictionary (merged with defaults).

    Raises:
        ConfigurationError: If a configuration value is invalid.
    """
    try:
        user_config = file_utils.load_json(str(paths.CONSTANTS_JSON))

    except ConfigurationError:
        # Config file missing or invalid - use defaults
        logger.warning('Config file not found or invalid, using defaults')
        merged = copy.deepcopy(DEFAULTS)

    else:
        logger.info('Loaded configuration from %s', paths.CONSTANTS_JSON)
        merged = _deep_merge(DEFAULTS, user_config)

    _validate_config(merged)
    return merged


# Load configuration at module import
_config = load_constants()

# API configuration
API_BATCH_SIZE: int = _config['api']['batch_size']
MAX_RETRIES: int = _config['api']['max_retries']
BASE_DELAY: int = _config['api']['base_delay_seconds']
MAX_BACKOFF: int = _config['api']['max_backoff_seconds']
DAILY_QUOTA: int = _config['api']['daily_quota']

# Network configuration
NETWORK_TIMEOUT: int = _config['network']['timeout_seconds']

# Quota budgets per job (accounting only; see yrt/youtube/quota.py)
DAILY_JOB_BUDGET: int = _config['quota']['daily_job_budget']
UPDATES_JOB_BUDGET: int = _config['quota']['updates_job_budget']

# Playlist configuration
RELEASE_RADAR_TARGET: int = _config['playlists']['release_radar_target_size']
RELISTENING_AGE_WEEKS: int = _config['playlists']['relistening_age_weeks']

# Video configuration
LONG_VIDEO_THRESHOLD_MINUTES: int = _config['video']['long_video_threshold_minutes']

# Statistics configuration
STATS_WEEK_DELTAS: list[int] = _config['stats']['week_deltas']
