# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

YouTube Release Tracker is an automated system that tracks the latest video releases from YouTube subscriptions and
categorizes them into specific playlists. The project uses YouTube Data API v3 with OAuth2 authentication.

The system automatically:

- Monitors specified YouTube channels for new uploads
- Categorizes videos based on channel type (music/other), duration, and favorite status
- Adds videos to appropriate playlists (Banger Radar, Release Radar, Watch Later)
- Tracks video statistics over time (views, likes, comments at 1, 4, 12, 24 week intervals)
- Manages playlist capacity by rotating content between playlists

## Development Commands

### Local Development

```bash
# Install dependencies
pip install -r requirements.txt

# Run the main process locally
cd src
python main.py local

# Sort the PocketTube database (standalone)
cd src
python youtube.py
```

### Testing & Linting

```bash
# Lint with flake8 (critical errors only)
flake8 . --count --select=E9,F63,F7,F82 --show-source --statistics

# Lint with flake8 (all issues, non-blocking)
flake8 . --count --exit-zero --max-complexity=10 --max-line-length=127 --statistics
```

### Encoding Authentication Files

For GitHub Actions deployment, authentication files need to be base64 encoded:

```python
from youtube import encode_key

encode_key(json_path='../tokens/credentials.json')
encode_key(json_path='../tokens/oauth.json')
```

## Architecture & Code Structure

### Execution Modes

The application supports two execution modes determined by `sys.argv[1]`:

1. **Local mode** (default): Uses `../tokens/oauth.json` and `../tokens/credentials.json` files for authentication.
   Displays progress bars with tqdm. Updates local credential files after execution.

2. **GitHub Actions mode** (`sys.argv[1] == 'action'`): Uses base64-encoded credentials from GitHub repository secrets (
   `CREDS_B64`). No progress bars. Updates the repository secret after execution if credentials were refreshed.

### Core Modules

**src/main.py**

- Entry point for the application
- Loads configuration from JSON files in `data/` directory
- Coordinates the video discovery and playlist management workflow
- Handles logging to `log/history.log` and `log/last_exe.log`
- Manages GitHub repository secrets updates in workflow mode
- Uses top-level exception handler for graceful error handling
- `copy_last_exe_log()` only runs on successful execution (failed runs don't update `last_exe.log`)

**src/youtube.py**

- Contains all YouTube API interaction functions
- Handles OAuth2 service creation for both local and GitHub Actions environments
- Implements video discovery via `iter_channels()` and `get_playlist_items()`
- Manages playlist operations: `add_to_playlist()`, `del_from_playlist()`
- Tracks video statistics over time with `weekly_stats()`
- Detects YouTube Shorts via HEAD request to `/shorts/{video_id}` endpoint
    - **Important**: Uses `allow_redirects=False` to distinguish shorts from regular videos
    - Real shorts return 200, regular videos return 3xx redirect to /watch?v= URL
- Handles API errors with intelligent retry mechanism:
    - **Transient errors** (`serviceUnavailable`, `backendError`, `internalError`): Retry up to 3 times with exponential
      backoff (1s, 2s, 4s)
    - **Permanent errors** (`videoNotFound`, `forbidden`, `duplicate`): Log and skip immediately
    - **Quota errors** (`quotaExceeded`): Save to `api_failure.json` for next-day retry
- Retries failed videos from previous runs via `add_api_fail()`

**src/paths.py**

- Centralized path definitions for the project
- Uses `Path(__file__).parent.parent.resolve()` for dynamic path resolution
- Exports all file and directory paths as constants (e.g., `DATA_DIR`, `POCKET_TUBE_JSON`, `HISTORY_LOG`)
- Allows running the script from any directory (not just `src/`)
- Defines `ALLOWED_DIRS` and `ALLOWED_EXTENSIONS` for `file_utils.py` validation

**src/file_utils.py**

- Centralized utility module for file operations
- Provides `load_json()` and `save_json()` with comprehensive error handling
- Implements path validation to prevent path traversal attacks
- Validates file paths against allowlists imported from `paths.py`
- All file operations logged to `history.log` with proper error messages

**src/exceptions.py**

- Custom exception hierarchy for the application
- `YouTubeTrackerError`: Base exception class
- `ConfigurationError`: Config file issues (missing, malformed, invalid keys)
- `FileAccessError`: Path validation failures (outside allowed directories, invalid extension)
- `YouTubeServiceError`: API service creation failures
- `CredentialsError`: Authentication/credential issues
- `APIError`: YouTube API call failures

**src/analytics.py**

- Placeholder for future analytics features
- Currently minimal implementation

### Configuration Files

All configuration is stored in JSON files in the `data/` directory:

- **pocket_tube.json**: Categorized list of YouTube channel IDs (MUSIQUE, APPRENTISSAGE, DIVERTISSEMENT, GAMING)
- **playlists.json**: Target playlist IDs and metadata
- **add-on.json**: Contains three lists:
    - `favorites`: Channels that should route to Banger Radar playlist
    - `playlistNotFoundPass`: Channels to ignore if their upload playlist returns 404
    - `toPass`: Channels to skip entirely during iteration
- **api_failure.json**: Tracks videos that failed to add due to API quota or transient errors (retried on next run)
- **stats.csv**: Historical data with video statistics at weekly intervals

### Video Routing Logic

The `dest_playlist()` function in main.py determines where each video goes:

1. **Shorts**: Return 'shorts' (ignored, not added anywhere)
2. **Music channels**:
    - If duration > 10 minutes AND channel is also in "other" categories: Watch Later
    - If duration > 10 minutes AND channel is music-only: 'none' (not added)
    - If channel is in favorites: Banger Radar
    - Otherwise: Release Radar
3. **Non-music channels**: Watch Later

### Playlist Management Strategy

**Release Radar Filling** (`fill_release_radar()` in youtube.py):

- Maintains a target of 40 videos in Release Radar playlist
- When below threshold, pulls videos from two sources:
    - Re-listening playlist (videos added at least 1 week ago)
    - Legacy playlist (older content to clear out)
- Uses proportional allocation based on source playlist sizes
- Moves videos (adds to Release Radar, removes from source)

### Authentication Flow

**Local Mode**:

1. Checks for existing `credentials.json`
2. If invalid/expired, attempts refresh using refresh token
3. If refresh fails, initiates OAuth2 flow via browser using `oauth.json`
4. Saves new credentials to `credentials.json`

**GitHub Actions Mode**:

1. Decodes `CREDS_B64` environment variable (base64-encoded JSON)
2. Creates Credentials object from decoded data
3. If expired, refreshes token and updates `CREDS_B64` environment variable
4. Updated credentials are saved back to repository secrets via GitHub API

### Date Handling & Filtering

- Uses `tzlocal` to get local timezone for timestamp comparisons
- `NOW` is the current datetime with timezone awareness
- `LAST_EXE` is parsed from `log/last_exe.log` first line (format: `%Y-%m-%d %H:%M:%S%z`)
- `get_playlist_items()` filters videos between `LAST_EXE` and `NOW` (or custom day range)
- All datetime comparisons round to the hour (XX:00:00) for consistency
- Scheduled videos and premieres (with `videoPublishedAt = None`) are automatically filtered out and picked up on the
  next run after going live

### Error Handling & Logging

- Uses Python's `logging` module with file handlers
- All logs written to `log/history.log` in append mode
- Format: `%(asctime)s [%(levelname)s] - %(message)s`
- `copy_last_exe_log()` extracts the most recent run's logs to `log/last_exe.log` (only on success)
- API failures (quota exceeded, video unavailable) are logged as warnings
- Failed video additions are saved to `api_failure.json` for retry on next run
- Custom exceptions (see `exceptions.py`) are used instead of `sys.exit()` for testability
- Top-level exception handler in `main.py` catches `YouTubeTrackerError` subclasses
- Unexpected exceptions are not caught - they fail with full traceback for debugging

### GitHub Actions Workflow

The workflow (`main_workflow.yml`) runs daily at 7:00 AM UTC:

1. Waits until midnight Pacific Time (handles PST/PDT automatically)
2. Sets up Python 3.11 environment
3. Installs dependencies from requirements.txt
4. Runs flake8 linting
5. Executes `main.py` in 'action' mode
6. Commits updated logs and stats.csv
7. Pushes changes back to repository

## Development Notes

### Working with YouTube API

- API requests are batched in chunks of 50 (max allowed per request)
- Service object is `pyt.Client` from `python-youtube` library (not `googleapiclient`)
- Playlist IDs: Upload playlists use `UU` prefix (replace `UC` in channel ID)
- Video statistics may return None for deleted/private videos
- Shorts detection requires a separate HTTP HEAD request (not available in API)

### Modifying Channel Lists or Playlists

Edit the JSON files in `data/` directory:

- Add/remove channels in `pocket_tube.json` under appropriate categories
- Update playlist IDs in `playlists.json` if playlists change
- Add favorite channels to `add-on.json` > `favorites` to route them to Banger Radar

### Weekly Statistics Collection

The `weekly_stats()` function runs on every execution:

- Checks for videos released exactly 1, 4, 12, or 24 weeks ago (at release date)
- Only collects stats if the corresponding `views_w{N}` column is NULL
- Updates stats in place within the DataFrame
- This ensures consistent tracking at specific time intervals after release
- **Optimization**: Skips shorts detection (`check_shorts=False`) since videos are already classified when first added

### Shorts Detection Optimization

The `get_stats()` function has a `check_shorts` parameter:

- `check_shorts=True` (default): Calls `is_shorts()` for each video (used for new videos via `add_stats()`)
- `check_shorts=False`: Skips the HTTP HEAD request (used by `weekly_stats()` for historical data)
- This avoids redundant network requests for videos already classified in `stats.csv`

### Repository Secrets

Required GitHub repository secrets:

- `CREDS_B64`: Base64-encoded OAuth2 credentials JSON
- `PAT`: Personal Access Token for updating repository secrets programmatically

### Code Quality

- DeepSource analyzes code quality automatically
- Python runtime: 3.x
- Max line length: 120 characters
- Avoid broad exception catching (use specific exception types)