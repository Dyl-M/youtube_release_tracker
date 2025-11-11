# -*- coding: utf-8 -*-

import json
import logging
import os
import sys

"""File Information
@file_name: file_utils.py
@author: Dylan "dyl-m" Monfret
Utility functions for file operations with error handling.
"""

"LOGGER"

# Create logger
logger = logging.Logger(name='file_utils', level=0)

# Create file handler
log_file = logging.FileHandler(filename='../log/history.log')  # mode='a'

# Create formatter
formatter = logging.Formatter(fmt='%(asctime)s [%(levelname)s] - %(message)s', datefmt='%Y-%m-%d %H:%M:%S%z')

# Set file handler level
log_file.setLevel(logging.DEBUG)

# Assign file handler and formatter to logger
log_file.setFormatter(formatter)
logger.addHandler(log_file)

"CONSTANTS"

# Allowed base directories for file operations (relative to src/)
ALLOWED_DIRS = ['../data', '../log', '../tokens']

# Allowed file extensions
ALLOWED_EXTENSIONS = ['.json', '.csv', '.log', '.txt']

"FUNCTIONS"


def validate_file_path(file_path: str):
    """Validate and sanitize file path to prevent path traversal attacks.

    :param file_path: Path to validate
    :return: Normalized absolute path if valid
    :raises SystemExit: If path is invalid or outside allowed directories
    """
    file_name = file_path.split('/')[-1]

    # Normalize the path to resolve any .. or . components
    normalized_path = os.path.normpath(file_path)

    # Check if the path starts with an allowed directory
    is_allowed = any(normalized_path.startswith(allowed_dir) for allowed_dir in ALLOWED_DIRS)

    if not is_allowed:
        logger.critical('Access denied: %s is outside allowed directories', file_path)
        logger.critical('Allowed directories: %s', ', '.join(ALLOWED_DIRS))
        sys.exit(1)

    # Check file extension
    file_ext = os.path.splitext(file_name)[1]
    if file_ext not in ALLOWED_EXTENSIONS:
        logger.critical('Invalid file type: %s (allowed: %s)', file_ext, ', '.join(ALLOWED_EXTENSIONS))
        sys.exit(1)

    return normalized_path


def load_json(file_path: str, required_keys: list = None):
    """Load a JSON file with comprehensive error handling.

    :param file_path: Path to the JSON file
    :param required_keys: Optional list of keys that must exist in the JSON
    :return: Parsed JSON data as dictionary
    """
    # Validate path for security
    validated_path = validate_file_path(file_path)
    file_name = file_path.split('/')[-1]

    try:
        with open(validated_path, 'r', encoding='utf8') as f:
            data = json.load(f)
    except FileNotFoundError:
        logger.critical('%s not found. Expected location: %s', file_name, file_path)
        logger.critical('Please ensure all required files exist.')
        sys.exit(1)
    except json.JSONDecodeError as e:
        logger.critical('%s is malformed: %s', file_name, str(e))
        logger.critical('Please check the JSON syntax.')
        sys.exit(1)
    except Exception as e:
        logger.critical('Unexpected error loading %s: %s', file_name, str(e))
        sys.exit(1)

    # Validate required keys if specified
    if required_keys:
        missing_keys = [key for key in required_keys if key not in data]
        if missing_keys:
            logger.critical('%s missing required keys: %s', file_name, ', '.join(missing_keys))
            sys.exit(1)

    return data


def save_json(file_path: str, data: dict, indent: int = 2):
    """Save data to a JSON file with error handling.

    :param file_path: Path to save the JSON file
    :param data: Dictionary to save as JSON
    :param indent: Indentation level for pretty printing (default: 2)
    """
    # Validate path for security
    validated_path = validate_file_path(file_path)
    file_name = file_path.split('/')[-1]

    try:
        with open(validated_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=indent)
    except IOError as e:
        logger.critical('Failed to write %s: %s', file_name, str(e))
        sys.exit(1)
    except Exception as e:
        logger.critical('Unexpected error saving %s: %s', file_name, str(e))
        sys.exit(1)


def validate_nested_keys(data: dict, key_path: list, file_name: str):
    """Validate nested dictionary keys exist.

    :param data: Dictionary to validate
    :param key_path: List of keys representing the path (e.g., ['playlists', 'release', 'id'])
    :param file_name: Name of file for error messages
    """
    current = data
    for key in key_path:
        if key not in current:
            path_str = ' -> '.join(key_path)
            logger.critical('%s missing key in path: %s', file_name, path_str)
            sys.exit(1)
        current = current[key]
