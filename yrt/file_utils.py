"""Utility functions for file operations with error handling."""

# Standard library
import json
import logging
import os
from typing import Any

# Local
from . import paths
from .exceptions import ConfigurationError, FileAccessError

# Create logger (only add file handler if not in standalone mode)
logger = logging.Logger(name='file_utils', level=0)

if not os.environ.get('YRT_NO_LOGGING'):
    # Create file handler
    log_file = logging.FileHandler(filename=paths.HISTORY_LOG)

    # Create formatter
    formatter = logging.Formatter(fmt='%(asctime)s [%(levelname)s] - %(message)s', datefmt='%Y-%m-%d %H:%M:%S%z')

    # Set file handler level
    log_file.setLevel(logging.DEBUG)

    # Assign file handler and formatter to logger
    log_file.setFormatter(formatter)
    logger.addHandler(log_file)

# Constants

# Import allowed directories and extensions from centralized paths module
ALLOWED_DIRS = paths.ALLOWED_DIRS
ALLOWED_EXTENSIONS = paths.ALLOWED_EXTENSIONS


# Functions


def validate_file_path(file_path: str) -> str:
    """Validate and sanitize file path to prevent path traversal attacks.

    Args:
        file_path: Path to validate (can be relative or absolute).

    Returns:
        Normalized absolute path if valid.

    Raises:
        FileAccessError: If path is invalid or outside allowed directories.
    """
    # Get the file name from the path (handle both / and \ separators)
    file_name = os.path.basename(file_path)

    # Normalize the path to resolve any .. or . components
    normalized_path = os.path.normpath(file_path)

    # Check if the path starts with an allowed directory (normalize allowed dirs for comparison)
    is_allowed = any(normalized_path.startswith(os.path.normpath(allowed_dir)) for allowed_dir in ALLOWED_DIRS)

    if not is_allowed:
        logger.critical('Access denied: %s is outside allowed directories', file_path)
        logger.critical('Allowed directories: %s', ', '.join(ALLOWED_DIRS))
        raise FileAccessError(f'Access denied: {file_path} is outside allowed directories')

    # Check file extension
    file_ext = os.path.splitext(file_name)[1]
    if file_ext not in ALLOWED_EXTENSIONS:
        logger.critical('Invalid file type: %s (allowed: %s)', file_ext, ', '.join(ALLOWED_EXTENSIONS))
        raise FileAccessError(f'Invalid file type: {file_ext}')

    return normalized_path


def load_json(file_path: str, required_keys: list[str] | None = None) -> dict[str, Any]:
    """Load a JSON file with comprehensive error handling.

    Args:
        file_path: Path to the JSON file.
        required_keys: Optional list of keys that must exist in the JSON.

    Returns:
        Parsed JSON data as dictionary.

    Raises:
        ConfigurationError: If file is missing, malformed, or missing required keys.
    """
    # Validate path for security
    validated_path = validate_file_path(file_path)
    file_name = os.path.basename(file_path)

    try:
        with open(validated_path, 'r', encoding='utf8') as f:
            data = json.load(f)

    except FileNotFoundError:
        logger.critical('%s not found. Expected location: %s', file_name, file_path)
        logger.critical('Please ensure all required files exist.')
        raise ConfigurationError(f'{file_name} not found at {file_path}')

    except json.JSONDecodeError as e:
        logger.critical('%s is malformed: %s', file_name, str(e))
        logger.critical('Please check the JSON syntax.')
        raise ConfigurationError(f'{file_name} is malformed: {e}')

    except Exception as e:
        logger.critical('Unexpected error loading %s: %s', file_name, str(e))
        raise ConfigurationError(f'Unexpected error loading {file_name}: {e}')

    # Validate required keys if specified
    if required_keys:
        missing_keys = [key for key in required_keys if key not in data]
        if missing_keys:
            logger.critical('%s missing required keys: %s', file_name, ', '.join(missing_keys))
            raise ConfigurationError(f'{file_name} missing required keys: {", ".join(missing_keys)}')

    return data  # type: ignore[no-any-return]


def save_json(file_path: str, data: dict[str, Any], indent: int = 2) -> None:
    """Save data to a JSON file with error handling.

    Args:
        file_path: Path to save the JSON file.
        data: Dictionary to save as JSON.
        indent: Indentation level for pretty printing (default: 2).

    Raises:
        ConfigurationError: If file cannot be written.
    """
    # Validate path for security
    validated_path = validate_file_path(file_path)
    file_name = os.path.basename(file_path)

    try:
        with open(validated_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=indent)

    except IOError as e:
        logger.critical('Failed to write %s: %s', file_name, str(e))
        raise ConfigurationError(f'Failed to write {file_name}: {e}')

    except Exception as e:
        logger.critical('Unexpected error saving %s: %s', file_name, str(e))
        raise ConfigurationError(f'Unexpected error saving {file_name}: {e}')


def validate_nested_keys(data: dict[str, Any], key_path: list[str], file_name: str) -> None:
    """Validate nested dictionary keys exist.

    Args:
        data: Dictionary to validate.
        key_path: List of keys to validate. Each key can use dot notation for nested paths (e.g., ['key1', 'key2']
            validates two top-level keys, ['level1.level2.key'] validates a nested path).
        file_name: Name of file for error messages.

    Raises:
        ConfigurationError: If a key in the path is missing.
    """
    for key in key_path:
        # Split on dot to support nested paths
        nested_keys = key.split('.')
        current: Any = data

        for nested_key in nested_keys:
            if not isinstance(current, dict):
                path_str = '.'.join(nested_keys)
                logger.critical('%s: path %s is not navigable (non-dict value encountered)', file_name, path_str)
                raise ConfigurationError(f'{file_name} missing key in path: {path_str}')

            if nested_key not in current:
                path_str = '.'.join(nested_keys)
                logger.critical('%s missing key in path: %s', file_name, path_str)
                raise ConfigurationError(f'{file_name} missing key in path: {path_str}')

            current = current[nested_key]
