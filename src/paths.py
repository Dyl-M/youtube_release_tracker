# -*- coding: utf-8 -*-

from pathlib import Path

"""File Information
@file_name: paths.py
@author: Dylan "dyl-m" Monfret
Centralized path definitions for the project. This module resolves paths dynamically based on the script location,
allowing the project to run from any directory.
"""

# Base directory (project root, one level up from src/)
BASE_DIR = Path(__file__).parent.parent.resolve()

# Directory paths
DATA_DIR = BASE_DIR / 'data'
LOG_DIR = BASE_DIR / 'log'
TOKENS_DIR = BASE_DIR / 'tokens'

# Data files
POCKET_TUBE_JSON = DATA_DIR / 'pocket_tube.json'
PLAYLISTS_JSON = DATA_DIR / 'playlists.json'
ADD_ON_JSON = DATA_DIR / 'add-on.json'
API_FAILURE_JSON = DATA_DIR / 'api_failure.json'
STATS_CSV = DATA_DIR / 'stats.csv'

# Log files
HISTORY_LOG = LOG_DIR / 'history.log'
LAST_EXE_LOG = LOG_DIR / 'last_exe.log'

# Token files
OAUTH_JSON = TOKENS_DIR / 'oauth.json'
CREDENTIALS_JSON = TOKENS_DIR / 'credentials.json'

# Allowed directories for file_utils validation (as strings for compatibility)
ALLOWED_DIRS = [str(DATA_DIR), str(LOG_DIR), str(TOKENS_DIR)]

# Allowed file extensions
ALLOWED_EXTENSIONS = ['.json', '.csv', '.log', '.txt']
