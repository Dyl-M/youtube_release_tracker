# -*- coding: utf-8 -*-

import json
import logging
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

"FUNCTIONS"


def load_json(file_path: str, required_keys: list = None):
    """Load a JSON file with comprehensive error handling.

    :param file_path: Path to the JSON file
    :param required_keys: Optional list of keys that must exist in the JSON
    :return: Parsed JSON data as dictionary
    """
    file_name = file_path.split('/')[-1]

    try:
        with open(file_path, 'r', encoding='utf8') as f:
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
    file_name = file_path.split('/')[-1]

    try:
        with open(file_path, 'w', encoding='utf-8') as f:
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
