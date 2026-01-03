"""Centralized path definitions for the project.

Resolves paths dynamically based on the script location, allowing the project to run from any directory.
"""

# Standard library
from pathlib import Path

# Base directory (project root, one level up from yrt/)
BASE_DIR: Path = Path(__file__).parent.parent.resolve()

# Directory paths
CONFIG_DIR: Path = BASE_DIR / '_config'
DATA_DIR: Path = BASE_DIR / '_data'
LOG_DIR: Path = BASE_DIR / '_log'
TOKENS_DIR: Path = BASE_DIR / '_tokens'
ARCHIVE_DIR: Path = BASE_DIR / '_archive'
ARCHIVE_DATA_DIR: Path = ARCHIVE_DIR / '_data'

# Config files (in _config/)
POCKET_TUBE_JSON: Path = CONFIG_DIR / 'pocket_tube.json'
PLAYLISTS_JSON: Path = CONFIG_DIR / 'playlists.json'
ADD_ON_JSON: Path = CONFIG_DIR / 'add-on.json'
API_FAILURE_JSON: Path = CONFIG_DIR / 'api_failure.json'
CONSTANTS_JSON: Path = CONFIG_DIR / 'constants.json'

# Data files (in _data/)
STATS_CSV: Path = DATA_DIR / 'stats.csv'

# Log files
HISTORY_LOG: Path = LOG_DIR / 'history.log'
LAST_EXE_LOG: Path = LOG_DIR / 'last_exe.log'

# Token files
OAUTH_JSON: Path = TOKENS_DIR / 'oauth.json'
CREDENTIALS_JSON: Path = TOKENS_DIR / 'credentials.json'

# Allowed directories for file_utils validation (as strings for compatibility)
ALLOWED_DIRS: list[str] = [str(CONFIG_DIR), str(DATA_DIR), str(LOG_DIR), str(TOKENS_DIR)]

# Allowed file extensions
ALLOWED_EXTENSIONS: list[str] = ['.json', '.csv', '.log', '.txt']
