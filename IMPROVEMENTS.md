# Repository Improvement Recommendations

Comprehensive analysis of the YouTube Release Tracker codebase identifying potential improvements, bugs, and
optimization opportunities.

## Critical Issues

### 1. ✅ FIXED - Network Request Without Timeout (Security/Reliability)

**Location:** `src/youtube.py:520-535`

**Status:** ✅ **FIXED**

**Issue:** No timeout specified, can hang indefinitely if YouTube is slow/unresponsive.

**Impact:** In workflow runs, this could cause the GitHub Action to hang until timeout (6 hours default).

**Fix Applied:**

- Added 5-second timeout to prevent hanging
- Added error handling for network failures
- Returns False (non-short) as safe default on errors
- Added logging for failed shorts detection
- Updated docstring to document error behavior

### 1a. ✅ FIXED - Incorrect Shorts Detection Due to HTTP Redirects (Critical Bug)

**Location:** `src/youtube.py:529`
**Related Issue:** #120

**Status:** ✅ **FIXED** (2025-11-12)

**Issue:** With `allow_redirects=True`, YouTube redirects regular videos from `/shorts/{video_id}` to
`/watch?v={video_id}`. This caused ALL videos to return status 200, incorrectly classifying every video as a Short.

**Impact:**

- All videos were misclassified as YouTube Shorts
- Video routing logic failed completely (shorts are ignored, not added to playlists)
- Historical data contained 433 duplicate entries with incorrect classifications
- Stats analysis was corrupted with wrong shorts/non-shorts ratios

**Root Cause:**

```python
# Before (BROKEN)
response = requests.head(
    f'https://www.youtube.com/shorts/{video_id}',
    timeout=5,
    allow_redirects=True  # ❌ Follows redirect, returns 200 for ALL videos
)
```

**Fix Applied:**

```python
# After (FIXED)
response = requests.head(
    f'https://www.youtube.com/shorts/{video_id}',
    timeout=5,
    allow_redirects=False  # ✅ Real shorts: 200, Regular videos: 3xx
)
```

**Verification:**

- Tested with 54 recent videos
- 16 correctly classified as shorts (11s-68s duration)
- 38 correctly classified as regular videos (100s-2229s duration)
- Before fix: 100% false positives (all marked as shorts)
- After fix: 95.6% accuracy for videos ≤60s, 97.9% accuracy for videos >90s

**Data Cleanup:**

- Removed 433 duplicate entries with incorrect shorts classification from stats.csv
- Final dataset: 24,595 unique videos
    - Shorts: 6,990 (28.4%, avg 41.5s)
    - Non-shorts: 17,605 (71.6%, avg 14 min)

### 2. ✅ FIXED - Missing Error Handling for Critical File Operations

**Location:** `src/main.py:38-110`

**Status:** ✅ **FIXED**

**Issue:** File operations at module level have no error handling. If any config file is missing/corrupted, the entire
script crashes with unhelpful error.

**Impact:** No graceful degradation, confusing error messages for users.

**Fix Applied:**

- Added try-except blocks for all JSON file loading (pocket_tube.json, playlists.json, add-on.json)
- Added specific error handling for FileNotFoundError and JSONDecodeError
- Added KeyError handling for missing required keys in config files
- All errors now display clear, actionable error messages before exiting

### 3. ✅ FIXED - Missing Encoding Parameter

**Location:** `src/main.py:62` (now line 62)

**Status:** ✅ **FIXED**

**Issue:** Inconsistent with other file opens - missing `encoding='utf8'`.

**Fix Applied:**

- Added `encoding='utf8'` to add-on.json file open for consistency with other file operations

### 4. ✅ FIXED - Stats CSV May Not Exist on First Run

**Location:** `src/main.py:100-110`

**Status:** ✅ **FIXED**

**Issue:** Will crash if file doesn't exist.

**Fix Applied:**

- Added check for file existence with `os.path.exists()`
- Creates empty DataFrame with correct schema if stats.csv doesn't exist
- Displays informational message when creating new file
- Full column specification ensures schema consistency

### 4a. ✅ FIXED - Videos Without Release Date Causing TypeError (Issue #104)

**Location:** `src/youtube.py:297-299` (get_playlist_items function)

**Related Issue:
** [#104 - Rare case of videos without Release Date](https://github.com/Dyl-M/youtube_release_tracker/issues/104)

**Status:** ✅ **FIXED** (2025-11-22)

**Issue:** Some videos returned by the YouTube API have `None` for `videoPublishedAt` field instead of an ISO 8601 date
string. This caused a `TypeError` when calling `datetime.strptime(None, date_format)`.

**Root Cause:** Scheduled videos and premieres that haven't aired yet don't have a published date. They appear in the
channel's upload playlist but with `videoPublishedAt = None`.

**Impact:**

- Workflow crashed with `TypeError` when encountering scheduled/premiere videos
- Process could not complete, leaving videos unprocessed

**Fix Applied:**

- Added filter condition in list comprehension to skip videos without release date
- Used walrus operator for efficient single-pass filtering:
  ```python
  p_items += [parsed for item in request.items
              if (parsed := _parse_playlist_item(item, ISO_DATE_FORMAT)) is not None]
  ```
- `_parse_playlist_item()` returns `None` for items without `videoPublishedAt`
- Scheduled videos will be picked up on the next run after they go live (with proper release date)

**Additional Refactoring:**

- Refactored `dest_playlist()` in main.py with flat structure and named boolean variables for clarity
- Reduced cyclomatic complexity in `get_playlist_items()` by extracting helper functions

## High Priority Issues

### 5. Excessive sys.exit() Calls

**Locations:** 10+ occurrences across `youtube.py` and `main.py`

**Issue:** Using `sys.exit()` terminates the entire program, making functions non-reusable and difficult to test.

**Impact:**

- Cannot use functions in other contexts (testing, notebooks)
- GitHub workflow commits incomplete data on error
- Difficult to implement retry logic

**Recommendation:**

- Raise custom exceptions instead
- Let caller decide whether to exit
- Add top-level exception handler in main.py

```python
# Define custom exceptions
class YouTubeServiceError(Exception):
    pass


class ConfigurationError(Exception):
    pass


# In functions, raise instead of exit
def encode_key(json_path: str, parameters):
    if 'tokens' not in json_path:
        raise ConfigurationError('FORBIDDEN ACCESS. Invalid file path.')
    if not os.path.exists(json_path):
        raise FileNotFoundError(f'{json_path} file does not exist.')
    # ... rest of function


# In main.py, wrap execution
if __name__ == '__main__':
    try:
        existing_code()
    except (YouTubeServiceError, ConfigurationError) as e:
        history_main.critical(f'Fatal error: {e}')
        sys.exit(1)
    except Exception as e:
        history_main.critical(f'Unexpected error: {e}')
        sys.exit(1)
```

### 6. ✅ FIXED - Broad Exception Catching

**Locations:** `youtube.py:156`, `youtube.py:203`, `main.py:133`

**Status:** ✅ **FIXED**

**Issue:** Caught ALL exceptions including KeyboardInterrupt, SystemExit, and programming errors.

**Fix Applied:**

- **youtube.py:156** (`create_service_local`): Now catches `(pyt.error.PyYouTubeException, ValueError, AttributeError)`
- **youtube.py:203** (`create_service_workflow`): Now catches
  `(pyt.error.PyYouTubeException, ValueError, AttributeError)`
- **main.py:133** (`update_repo_secrets`): Now catches `(github.GithubException, ValueError)`
- All exception handlers now catch only specific, expected exceptions

### 7. ✅ FIXED - Performance: is_shorts() Called for Every Video

**Location:** `src/youtube.py:372` (get_stats function)

**Status:** ✅ **FIXED** (2025-11-23)

**Issue:** Made an HTTP HEAD request for every single video, even when checking stats for historical videos that were
already classified.

**Impact:**

- Slowed down execution during `weekly_stats()` calls
- Wasted network bandwidth
- Could trigger rate limiting from YouTube

**Fix Applied:**

- Added `check_shorts: bool = True` parameter to `get_stats()` function
- New videos via `add_stats()`: Uses default `check_shorts=True` to classify videos
- Historical stats via `weekly_stats()`: Now passes `check_shorts=False` to skip redundant HTTP requests
- Videos are classified once when first added and the result is stored in `stats.csv`

```python
# get_stats() now has check_shorts parameter
def get_stats(service: pyt.Client, videos_list: list, check_shorts: bool = True):
    ...
    'is_shorts': is_shorts(video_id=item.id) if check_shorts else None,
    ...

# weekly_stats() skips shorts detection for historical data
stats = pd.DataFrame(get_stats(service, vid_id_list, check_shorts=False))[to_keep]
```

### 8. ✅ FIXED - Transient API Error Handling (GCP Service Unavailability)

**Location:** `src/youtube.py:447-478` (add_to_playlist function)

**Related Issue:
** [#103 - Handling GCP Service Unavailability](https://github.com/Dyl-M/youtube_release_tracker/issues/103)

**Status:** ✅ **FIXED** (2025-11-22)

**Issue:** All API errors were treated equally without differentiating between:

- **Transient errors** (`serviceUnavailable`, `backendError`, `internalError`) - temporary GCP issues that could
  succeed with immediate retry
- **Quota errors** (`quotaExceeded`) - need to wait until quota resets
- **Permanent errors** (`videoNotFound`, `forbidden`, `duplicate`) - will never succeed

Previously, all failures immediately went to `api_failure.json` for next-run retry (24 hours later), even transient
errors that could succeed with immediate exponential backoff retry.

**Impact:**

- Transient GCP infrastructure hiccups caused 24-hour delays instead of immediate resolution
- No visibility into error types and patterns
- Videos accumulated in api_failure.json unnecessarily

**Fix Applied:**

- Added error categorization constants at module level:
  ```python
  TRANSIENT_ERRORS = ['serviceUnavailable', 'backendError', 'internalError']
  PERMANENT_ERRORS = ['videoNotFound', 'forbidden', 'playlistOperationUnsupported', 'duplicate']
  QUOTA_ERRORS = ['quotaExceeded']
  MAX_RETRIES = 3
  ```
- Implemented retry loop with exponential backoff (1s, 2s, 4s) for transient errors
- Permanent errors are now logged and skipped immediately (no retry)
- Only quota errors and exhausted transient retries are saved to `api_failure.json`
- Fixed `add_api_fail()` to preserve video IDs that fail again on retry (previously lost due to premature list clearing)

### 9. Hardcoded Relative Paths

**Locations:** Throughout codebase (`../data/`, `../log/`, `../tokens/`)

**Issue:**

- Only works when running from `src/` directory
- Breaks if script is called from different location
- Makes testing difficult

**Recommendation:** Use path resolution:

```python
import os
from pathlib import Path

# At top of file
BASE_DIR = Path(__file__).parent.parent.resolve()
DATA_DIR = BASE_DIR / 'data'
LOG_DIR = BASE_DIR / 'log'
TOKENS_DIR = BASE_DIR / 'tokens'

# Usage
with open(DATA_DIR / 'pocket_tube.json', 'r', encoding='utf8') as f:
    pocket_tube = json.load(f)
```

## Medium Priority Issues

### 10. No Unit Tests

**Issue:** No test files found in repository.

**Recommendation:** Add pytest and create tests:

```
tests/
  test_youtube.py
  test_main.py
  test_data_validation.py
  fixtures/
    sample_playlist_response.json
    sample_video_stats.json
```

Key functions to test:

- `dest_playlist()` - routing logic
- `get_playlist_items()` - date filtering
- `weekly_stats()` - data updates
- `is_shorts()` - with mocked requests

### 11. No Configuration File

**Issue:** Magic numbers scattered throughout code (40, 50, 10, etc.)

**Recommendation:** Create `config.json`:

```json
{
  "api": {
    "max_results_per_request": 50,
    "request_timeout": 5
  },
  "playlists": {
    "release_radar_target_size": 40,
    "max_video_duration_minutes": 10
  },
  "stats": {
    "week_deltas": [
      1,
      4,
      12,
      24
    ]
  }
}
```

### 12. Workflow Force Push

**Location:** `.github/workflows/main_workflow.yml:110`

```yaml
force: true
```

**Issue:** Force pushing can cause data loss if manual commits were made.

**Recommendation:** Remove force flag. If there are conflicts, fail the workflow and investigate.

### 13. No Type Hints

**Issue:** Python 3.11 has excellent type hint support, but code has none.

**Benefits of adding type hints:**

- Catch bugs at development time with mypy
- Better IDE autocomplete
- Self-documenting code

**Recommendation:** Add type hints gradually:

```python
from typing import List, Dict, Optional
import pyyoutube as pyt


def get_playlist_items(
        service: pyt.Client,
        playlist_id: str,
        day_ago: Optional[int] = None,
        latest_d: dt.datetime = NOW
) -> List[Dict[str, any]]:
    ...
```

### 14. Deprecated Functions File Still in Repo

**Location:** `src/deprecated_functions.py`

**Issue:** Contains old code that's no longer used (243 lines).

**Recommendation:**

- If truly deprecated, remove it (git history preserves it)
- If might be needed, move to `archive/` directory (already gitignored)

### 15. Sandbox File in Repository

**Location:** `src/_sandbox.py`

**Issue:** Likely experimental/test code. Should not be in production codebase.

**Recommendation:** Delete or add to .gitignore if used for local testing.

### 16. Log File Race Condition

**Location:** `src/youtube.py:42-58` and module-level execution

**Issue:** `last_exe_date()` runs at module import, but `last_exe.log` might not exist yet or might be empty.

**Recommendation:**

```python
def last_exe_date() -> Optional[dt.datetime]:
    try:
        with open('../log/last_exe.log', 'r', encoding='utf8') as log_file:
            lines = log_file.readlines()
            if not lines:
                return None
            first_log = lines[0]
        d_str = re.search(r'(\d{4}(-\d{2}){2})\s(\d{2}:?){3}.[\d:]+', first_log).group()
        return dt.datetime.strptime(d_str, '%Y-%m-%d %H:%M:%S%z')
    except (FileNotFoundError, IndexError, AttributeError):
        # On first run, default to 7 days ago
        return dt.datetime.now(tz=tzlocal.get_localzone()) - dt.timedelta(days=7)
```

## Low Priority / Nice to Have

### 17. Environment Variables Not Validated

**Location:** `src/main.py:21-27`

**Recommendation:** Add validation for GitHub Actions mode:

```python
try:
    github_repo = os.environ['GITHUB_REPOSITORY']
    PAT = os.environ['PAT']
    if not PAT or not github_repo:
        raise ValueError("Environment variables are empty")
except KeyError as e:
    if len(sys.argv) > 1 and sys.argv[1] == 'action':
        print(f"ERROR: Required environment variable {e} not set")
        sys.exit(1)
    # Fall back to local mode
    github_repo = 'Dyl-M/auto_youtube_playlist'
    PAT = 'PAT'
```

### 18. Workflow Timezone Logic Could Be Simplified

**Location:** `.github/workflows/main_workflow.yml:49-66`

**Issue:** Complex bash loop checking every minute.

**Alternative:** Use a GitHub Action like `schedule-timezone` or pre-calculate the UTC time that corresponds to midnight
PT.

### 19. No Data Backup Mechanism

**Recommendation:** Add a workflow step to backup `data/stats.csv` periodically:

```yaml
- name: Backup stats
  if: github.event_name == 'schedule' && github.event.schedule == '0 0 * * 0'  # Weekly
  run: |
    mkdir -p archive
    cp data/stats.csv archive/stats_$(date +%Y%m%d).csv
```

### 20. stats.csv Could Grow Large

**Current size:** Unknown, but tracking videos since at least 2024-07-24.

**Recommendation:**

- Add periodic archiving of old entries (>6 months)
- Consider database instead of CSV for better performance
- Add index/partition by date

### 21. No Notification on Workflow Failure

**Recommendation:** Add GitHub Action to send notification on failure:

```yaml
- name: Notify on failure
  if: failure()
  uses: actions/github-script@v6
  with:
    script: |
      github.rest.issues.create({
        owner: context.repo.owner,
        repo: context.repo.repo,
        title: 'Workflow failed: ' + context.workflow,
        body: 'Check logs: ' + context.serverUrl + '/' + context.repo.owner + '/' + context.repo.repo + '/actions/runs/' + context.runId
      })
```

### 22. CLAUDE.md in .gitignore

**Location:** `.gitignore:141`

**Issue:** CLAUDE.md is ignored by git, but it should be versioned.

**Recommendation:** Remove from .gitignore or create a local-only version like CLAUDE_LOCAL.md.

### 23. Improve Docstrings

**Issue:** Some docstrings use inconsistent formats.

**Recommendation:** Adopt Google or NumPy docstring style consistently:

```python
def get_playlist_items(service: pyt.Client, playlist_id: str, day_ago: int = None, latest_d: dt.datetime = NOW):
    """Get the videos in a YouTube playlist.

    Args:
        service: A Python YouTube Client.
        playlist_id: A YouTube playlist ID.
        day_ago: Day difference with a reference date, delimits items' collection field.
        latest_d: The latest reference date.

    Returns:
        List of playlist items (videos) with metadata.

    Raises:
        PyYouTubeException: If playlist not found or API error occurs.
    """
```

## Additional Improvements (Beyond Original List)

### 24. ✅ FIXED - Path Validation Windows Compatibility

**Location:** `src/file_utils.py:56`

**Status:** ✅ **FIXED** (2025-11-12)

**Issue:** Path validation failed on Windows due to path separator inconsistency. `os.path.normpath()` converts forward
slashes to backslashes on Windows (e.g., `../data` becomes `..\data`), but the comparison was checking if
`..\data\file.json` starts with `../data`, which always failed.

**Impact:**

- Script crashed on Windows with "Access denied: ../data/add-on.json is outside allowed directories"
- Prevented execution in local mode on Windows systems
- Affected all file operations (data, logs, tokens)

**Root Cause:**

```python
# Before (BROKEN on Windows)
normalized_path = os.path.normpath(file_path)  # Returns ..\data\file.json
is_allowed = any(normalized_path.startswith(allowed_dir) for allowed_dir in ALLOWED_DIRS)
# Compares ..\data\file.json with ../data → False
```

**Fix Applied:**

```python
# After (FIXED for all platforms)
normalized_path = os.path.normpath(file_path)
is_allowed = any(normalized_path.startswith(os.path.normpath(allowed_dir)) for allowed_dir in ALLOWED_DIRS)
# Compares ..\data\file.json with ..\data → True
```

**Verification:**

- Tested on Windows in local mode
- All file operations now work correctly
- Cross-platform compatibility maintained (Linux/macOS unaffected)

### 25. ✅ COMPLETED - Refactored Redundant File Handling Code

**Locations:** `src/main.py`, `src/youtube.py`, `src/file_utils.py`

**Status:** ✅ **COMPLETED**

**Issue:** Repetitive try-except blocks for JSON file loading throughout the codebase, violating DRY principle.

**Fix Applied:**

- Created new utility module `src/file_utils.py` with reusable functions:
    - `load_json()`: Load JSON with comprehensive error handling and optional key validation
    - `save_json()`: Save JSON with error handling and consistent formatting (indent=2)
    - `validate_nested_keys()`: Validate nested dictionary structures
    - Proper logging setup using Python's `logging` module (not print statements)
    - All errors logged to `history.log` with timestamps and severity levels
- Refactored main.py: Reduced 70+ lines of redundant error handling to 3 clean declarative calls
- Refactored youtube.py: Replaced 6 instances of manual JSON operations with utility functions
- All file operations now have consistent error handling and messages
- Code is now more maintainable and DRY-compliant

**Logging Improvements:**

- Replaced `print()` statements with proper `logger.critical()` calls
- Configured logger to write to `../log/history.log` (consistent with rest of codebase)
- Uses same formatter as `youtube.py` and `main.py`: `%(asctime)s [%(levelname)s] - %(message)s`
- All configuration file errors now properly logged and traceable
- Better debugging for GitHub Actions workflow runs

**Lines Reduced:**

- main.py: ~70 lines → ~15 lines (78% reduction in file handling code)
- youtube.py: ~36 lines → ~6 lines (83% reduction in file handling code)

## Summary

**Critical:** ~~4~~ **0** issues requiring immediate attention (✅ All Fixed!)
**DeepSource:** ~~4~~ **0** code quality issues (✅ All Fixed!)
**High Priority:** ~~5~~ **2** issues that significantly impact reliability/performance (✅ 3 Fixed!)
**Medium Priority:** 9 issues that improve maintainability
**Low Priority:** 9 nice-to-have improvements
**Additional Improvements:** 2 fixes completed, 1 major refactoring completed

**Completed Fixes:**

1. ✅ Network timeout for is_shorts() HTTP requests (Critical #1)
2. ✅ Shorts detection HTTP redirect bug - Issue #120 (Critical #1a)
3. ✅ Error handling for all config file operations (Critical #2)
4. ✅ Added encoding parameter to add-on.json (Critical #3)
5. ✅ Handle missing stats.csv on first run (Critical #4)
6. ✅ Path validation Windows compatibility (Additional #24)
7. ✅ Overlapping exception handlers in youtube.py (DeepSource #5)
8. ✅ Unused import in main.py (DeepSource #6)
9. ✅ Path traversal vulnerability in file_utils.py (DeepSource #7)
10. ✅ Unused function parameter in file_utils.py (DeepSource #8)
11. ✅ Broad exception catching replaced with specific exceptions (High Priority #6)
12. ✅ Created file_utils.py module and eliminated all redundant file handling code (Refactoring #25)
13. ✅ Transient API error handling with retry logic - Issue #103 (High Priority #8)
14. ✅ Videos without release date causing TypeError - Issue #104 (Critical #4a)
15. ✅ **Shorts detection optimization - skip HTTP requests for historical stats (High Priority #7)** ← **NEW (2025-11-23)**

**Latest Session Impact (2025-11-23):**

- Added `check_shorts` parameter to `get_stats()` function for conditional shorts detection
- `weekly_stats()` now skips shorts detection for historical videos (already classified)
- Reduces redundant HTTP HEAD requests during weekly statistics collection
- Improves execution speed and reduces network bandwidth usage

**Previous Session Impact (2025-11-22):**

- Implemented intelligent API error handling with exponential backoff retry for transient errors
- Transient GCP errors (serviceUnavailable, backendError, internalError) now retry up to 3 times with 1s, 2s, 4s delays
- Permanent errors (videoNotFound, forbidden, duplicate) are logged and skipped immediately
- Fixed bug in `add_api_fail()` where video IDs were lost if they failed again on retry
- Replaced broad exception catches with specific exception types across the codebase
- Fixed TypeError when videos have no release date (scheduled/premieres) - now filtered out gracefully
- Refactored `dest_playlist()` with cleaner flat structure and named boolean variables
- Reduced cyclomatic complexity in `get_playlist_items()` by extracting helper functions

**Code Quality Impact:**

- ~106 lines of redundant code eliminated (from previous refactoring)
- All JSON file operations now use centralized error handling
- Consistent error messages across the codebase
- Path traversal attacks prevented with allowlist validation
- All DeepSource code quality warnings resolved
- Exception handlers now catch only specific, expected exceptions
- Easier to add new configuration files in the future
- Fixed data integrity issues in stats.csv
- API errors now handled intelligently based on error type
- Optimized network usage by skipping redundant shorts detection

**Recommended Priority Order (Remaining):**

1. Fix hardcoded paths (High #9) - Developer experience improvement
2. Replace sys.exit() with exceptions (High #5) - Code quality (best done after other refactors)
3. Add basic unit tests (Medium #10)
4. Create configuration file (Medium #11)
5. Address remaining issues as time permits
