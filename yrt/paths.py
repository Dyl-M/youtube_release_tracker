# -*- coding: utf-8 -*-

from pathlib import Path

"""File Information
@file_name: paths.py
@author: Dylan "dyl-m" Monfret
Centralized path definitions for the project. This module resolves paths dynamically based on the script location,
allowing the project to run from any directory.
"""

# Base directory (project root, one level up from yrt/)
BASE_DIR = Path(__file__).parent.parent.resolve()

# Directory paths
CONFIG_DIR = BASE_DIR / '_config'
DATA_DIR = BASE_DIR / '_data'
LOG_DIR = BASE_DIR / '_log'
TOKENS_DIR = BASE_DIR / '_tokens'

# Config files (in _config/)
POCKET_TUBE_JSON = CONFIG_DIR / 'pocket_tube.json'
PLAYLISTS_JSON = CONFIG_DIR / 'playlists.json'
ADD_ON_JSON = CONFIG_DIR / 'add-on.json'
API_FAILURE_JSON = CONFIG_DIR / 'api_failure.json'
CONSTANTS_JSON = CONFIG_DIR / 'constants.json'

# Data files (in _data/)
STATS_CSV = DATA_DIR / 'stats.csv'

# Log files
HISTORY_LOG = LOG_DIR / 'history.log'
LAST_EXE_LOG = LOG_DIR / 'last_exe.log'

# Token files
OAUTH_JSON = TOKENS_DIR / 'oauth.json'
CREDENTIALS_JSON = TOKENS_DIR / 'credentials.json'

# Allowed directories for file_utils validation (as strings for compatibility)
ALLOWED_DIRS = [str(CONFIG_DIR), str(DATA_DIR), str(LOG_DIR), str(TOKENS_DIR)]

# Allowed file extensions
ALLOWED_EXTENSIONS = ['.json', '.csv', '.log', '.txt']
