# Repository Improvement Recommendations - 2026

Comprehensive analysis of the YouTube Release Tracker codebase identifying potential improvements for maintainability,
Pythonic implementation, and readability.

## 🎯 Goals

- **Logging:** Only the main process (`yrt/main.py`) should generate logs. Utility scripts and modules should not write
  to log files (or at least, not leave any traces).
- **Test Coverage:** Target 90% code coverage by the end of improvements (reported to DeepSource). Coverage should
  improve incrementally phase by phase.
    - **Baseline (Phase 1 complete):** 43% code coverage (177 tests passing)
    - **Note:** This is *code line coverage*, not *test pass rate* (which is 88.5%)

---

## ☢️ Critical Issues

### 1. BUG: file_utils.py Missing YRT_NO_LOGGING Check

**Location:** `yrt/file_utils.py:14-28`

**Status:** ✅ Fixed

**Issue:** Unlike `config.py:15` and `youtube.py:82`, file_utils.py unconditionally creates a file handler, causing
scripts to log to `history.log` when they shouldn't (even when `YRT_NO_LOGGING=1` is set).

**Impact:** When running `archive_data.py` or `sort_db.py`, file operations still log despite disabling logging.

**Fix:** Add conditional check around logger file handler setup:

```python
if not os.environ.get('YRT_NO_LOGGING'):
    log_file = logging.FileHandler(filename=paths.HISTORY_LOG)
    # ... rest of handler setup
```

---

## ⚠️ High Priority - Structural Improvements

### 2. Extract Logger Factory (DRY Violation)

**Locations:**

- `yrt/file_utils.py:14-27`
- `yrt/config.py:13-27`
- `yrt/youtube.py:79-94`
- `yrt/main.py:157-170`

**Status:** ✅ Fixed

**Issue:** Same ~15-line logger setup pattern duplicated 4 times across modules.

**Impact:** Code duplication, inconsistent logging configuration, harder maintenance.

**Solution:** Create `yrt/logging_utils.py`:

```python
"""Logging utilities for consistent logger configuration."""

import logging
import os
from pathlib import Path


def create_file_logger(
        name: str,
        log_file: Path,
        level: int = logging.DEBUG,
        respect_no_logging: bool = True
) -> logging.Logger:
    """Create a standardized file logger.

    Args:
        name: Logger name.
        log_file: Path to log file.
        level: Logging level.
        respect_no_logging: Whether to check YRT_NO_LOGGING environment variable.

    Returns:
        Configured logger instance.
    """
    logger = logging.Logger(name=name, level=0)

    if respect_no_logging and os.environ.get('YRT_NO_LOGGING'):
        return logger

    handler = logging.FileHandler(filename=log_file)
    handler.setLevel(level)

    formatter = logging.Formatter(
        fmt='%(asctime)s [%(levelname)s] - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S%z'
    )

    handler.setFormatter(formatter)
    logger.addHandler(handler)

    return logger
```

### 3. Split youtube.py Into Focused Modules

**Location:** `yrt/youtube.py` (1195 lines)

**Status:** ✅ Fixed

**Issue:** Single file handling too many responsibilities - authentication, API calls, statistics, playlist management,
cleanup, and utilities.

**Impact:** Hard to navigate, test, and extend. Circular import risks as module grows.

**Implemented structure:**

```
yrt/
  youtube/
    __init__.py       # Public API exports, shared logger setup
    auth.py           # Authentication (create_service_local, create_service_workflow, encode_key)
    api.py            # Core API calls (get_playlist_items, get_videos, get_subs, iter_channels)
    stats.py          # Statistics (get_stats, add_stats, weekly_stats)
    playlist.py       # Playlist operations (add_to_playlist, del_from_playlist, fill_release_radar)
    cleanup.py        # Cleanup (cleanup_expired_videos, cleanup_ended_streams)
    utils.py          # Utilities (is_shorts, last_exe_date, sort_db, get_items_count, constants)
```

Note: `models.py` and `retry.py` deferred to Point 4 and Point 8 respectively (separate concerns).

### 4. Create Domain Models with Dataclasses

**Location:** Throughout codebase (heavy use of `dict[str, Any]`)

**Status:** ✅ Fixed

**Issue:** No type-safe domain models. Functions return and accept generic dictionaries, losing IDE support and type
checking benefits.

**Solution Implemented:** Created dataclasses in `yrt/models.py`:

**Dataclasses created:**

- `PlaylistConfig` - Playlist metadata with validation
- `AddOnConfig` - Favorites and filters configuration
- `PlaylistItem` - Core video data with source_channel_id
- `VideoStats` - Video statistics (views, likes, duration, etc.)
- `VideoData` - Combined PlaylistItem + VideoStats (factory method pattern)
- `PlaylistItemRef` - Lightweight reference for playlist operations

**Helper functions:**

- `to_dict()` - Convert dataclass to dict with datetime serialization
- `to_dict_list()` - Batch convert for pandas DataFrame integration

**Key improvements:**

- Eliminated ~150+ instances of `dict[str, Any]` throughout codebase
- Full IDE autocomplete and type checking support
- Validation in `__post_init__` methods
- No mutation: source_channel_id set at creation time
- 26 comprehensive unit tests added
- Zero regressions (100 tests passing)

### 5. Extract VideoRouter Class from dest_playlist()

**Location:** `yrt/main.py:213-280`

**Status:** ✅ Fixed

**Issue:** Complex nested conditions in `dest_playlist()` function. Hard to test, extend, and understand.

**Impact:** Business-critical routing logic buried in complex conditionals.

**Solution Implemented:** Created `yrt/router.py` with:

- `RouterConfig` dataclass for routing configuration with validation
- `VideoRouter` class with clear routing methods
- Factory function `create_router_from_config()` for easy instantiation
- Module-level singleton `video_router` in main.py
- `dest_playlist()` now delegates to router (backward compatible)
- 40 comprehensive unit tests covering all routing paths

**Original Solution (reference):** Create `VideoRouter` class:

```python
class VideoRouter:
    """Routes videos to appropriate playlists based on channel category and video properties."""

    def __init__(
            self,
            music_channels: set[str],
            favorites: set[str],
            category_mapping: dict[str, set[str]],
            playlist_ids: dict[str, str]
    ):
        self.music_channels = music_channels
        self.favorites = favorites
        self.category_mapping = category_mapping
        self.playlist_ids = playlist_ids

    def route_video(
            self,
            channel_id: str,
            is_shorts: bool,
            duration_seconds: int,
            live_status: str = 'none'
    ) -> str:
        """Determine destination playlist for a video."""
        if live_status == 'upcoming':
            return self._route_stream(channel_id)

        if is_shorts:
            return 'shorts'

        if channel_id in self.music_channels:
            return self._route_music_video(channel_id, duration_seconds)

        return self._route_non_music_video(channel_id)

    def _route_stream(self, channel_id: str) -> str:
        """Route upcoming streams to appropriate playlist."""
        return (
            self.playlist_ids['music_lives']
            if channel_id in self.music_channels
            else self.playlist_ids['regular_streams']
        )

    def _route_music_video(self, channel_id: str, duration: int) -> str:
        """Route music channel videos."""
        # ... routing logic

    def _route_non_music_video(self, channel_id: str) -> str:
        """Route non-music channel videos to category playlists."""
        # ... routing logic
```

### 6. Create Constants Module

**Location:** Magic strings scattered throughout codebase

**Status:** ✅ Fixed

**Issue:** Magic strings for video routing, live statuses, error categories, and date formats.

**Solution Implemented:** Created `yrt/constants.py` with:

- `ROUTING_SHORTS`, `ROUTING_NONE` - Video routing destinations
- `LIVE_STATUS_NONE`, `LIVE_STATUS_UPCOMING`, `LIVE_STATUS_LIVE` - Live broadcast statuses
- `STATUS_PUBLIC`, `STATUS_UNLISTED`, `STATUS_PRIVATE`, `STATUS_DELETED` - Privacy statuses
- `TRANSIENT_ERRORS`, `PERMANENT_ERRORS`, `QUOTA_ERRORS` - API error categories (frozensets)
- `ISO_DATE_FORMAT`, `LOG_DATE_FORMAT` - Date/time formats
- `CHANNEL_PREFIX`, `UPLOAD_PLAYLIST_PREFIX` - YouTube ID prefixes
- `CATEGORY_MUSIC`, `CATEGORY_LEARNING`, `CATEGORY_ENTERTAINMENT`, `CATEGORY_GAMING`, `CATEGORY_ASMR` - Channel
  categories
- `CATEGORY_PRIORITY` - Category routing priority order

**Files modified:**

- `yrt/constants.py` - Created with all constants
- `yrt/youtube/utils.py` - Removed error sets, re-exports from constants for backward compatibility
- `yrt/router.py` - Imports routing and category constants
- `yrt/models.py` - Imports status constants for defaults
- `yrt/youtube/cleanup.py` - Imports live status constants
- `yrt/youtube/stats.py` - Imports STATUS_DELETED constant
- `yrt/main.py` - Imports LIVE_STATUS_UPCOMING constant
- `yrt/__init__.py` - Added 'constants' to exports
- `_tests/test_constants.py` - Created with 37 comprehensive tests

---

## 🛑 Medium Priority - Code Quality

### 7. Use pathlib Consistently

**Locations:**

- `yrt/file_utils.py:58-63` - Uses string operations for path validation
- `yrt/main.py:144-154` - Manual file I/O in `copy_last_exe_log()`

**Status:** Pending

**Issue:** Mixed use of `os.path` string operations and `pathlib.Path` objects.

**Solution:** Use `Path.is_relative_to()` for validation, `Path.read_text()`/`Path.write_text()` for I/O:

```python
def validate_file_path(file_path: str | Path) -> Path:
    """Validate and sanitize file path to prevent path traversal attacks."""
    path = Path(file_path).resolve()

    is_allowed = any(
        path.is_relative_to(allowed_dir)
        for allowed_dir in ALLOWED_DIRS
    )

    if not is_allowed:
        raise FileAccessError(f"Access denied: {path} is outside allowed directories")

    return path
```

### 8. Extract Retry Logic to Decorator

**Location:** `yrt/youtube.py:576-640` (`add_to_playlist` function)

**Status:** Pending

**Issue:** Retry logic with exponential backoff embedded directly in function, making it hard to reuse.

**Solution:** Create reusable decorator in `yrt/youtube/retry.py`:

```python
from functools import wraps
import time
import random
import math


def retry_with_backoff(
        max_retries: int = 3,
        transient_errors: set[str] = TRANSIENT_ERRORS,
        base_delay: float = 1.0,
        max_backoff: float = 32.0
):
    """Decorator for retrying API calls with exponential backoff and jitter."""

    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            for attempt in range(max_retries):
                try:
                    return func(*args, **kwargs)
                except pyt.error.PyYouTubeException as error:
                    error_reason = _extract_error_reason(error)

                    if error_reason not in transient_errors:
                        raise

                    if attempt == max_retries - 1:
                        raise

                    delay = min(max_backoff, base_delay * math.exp(attempt))
                    wait_time = delay / 2 + random.uniform(0, delay / 2)
                    time.sleep(wait_time)

            raise RuntimeError(f"Max retries ({max_retries}) exceeded")

        return wrapper

    return decorator
```

### 9. Add Config Validation

**Location:** `yrt/config.py:75-89`

**Status:** Pending

**Issue:** No validation of configuration values. Negative numbers, zero batch sizes, or invalid values aren't caught.

**Solution:** Add validation function:

```python
def _validate_config(config: dict) -> None:
    """Validate configuration values are within acceptable ranges."""
    api_batch = config['api']['batch_size']
    if not 1 <= api_batch <= 50:
        raise ConfigurationError(f"API batch_size must be 1-50, got {api_batch}")

    max_retries = config['api']['max_retries']
    if max_retries < 0:
        raise ConfigurationError(f"max_retries must be >= 0, got {max_retries}")

    timeout = config['network']['timeout_seconds']
    if timeout <= 0:
        raise ConfigurationError(f"timeout must be > 0, got {timeout}")
```

### 10. Fix Module-Level Datetime Calculation

**Location:** `yrt/youtube.py:76-77`

**Status:** Pending

**Issue:** `NOW` and `LAST_EXE` calculated at import time, making testing difficult and causing stale values in
long-running processes.

**Solution:** Use functions or context object:

```python
@dataclass
class ExecutionContext:
    """Execution context for time-dependent operations."""
    now: dt.datetime = field(default_factory=lambda: dt.datetime.now(tz=tzlocal.get_localzone()))
    last_exe: dt.datetime = field(default_factory=last_exe_date)


def get_execution_context() -> ExecutionContext:
    """Get fresh execution context."""
    return ExecutionContext()
```

### 11. Remove/Relocate Unused Files

**Files:**

- `yrt/analytics.py` - Placeholder with only pandas options and print statement
- `yrt/_sandbox.py` - Empty development scratch space

**Status:** Pending

**Issue:** Files serve no purpose in production codebase.

**Solution:**

- Remove `analytics.py` entirely or add clear "NOT IMPLEMENTED" docstring
- Keep `_sandbox.py` in `.gitignore` only (already done)

---

## 🧪 Test Suite Improvements

### 12. Prevent Test Suite from Writing to Log Files

**Location:** `_tests/conftest.py`

**Status:** ✅ Fixed

**Issue:** Several yrt modules create loggers at import time (module-level):

- `yrt/config.py:10` - `logger = create_file_logger('config', paths.HISTORY_LOG)`
- `yrt/file_utils.py:14` - `logger = create_file_logger('file_utils', paths.HISTORY_LOG)`
- `yrt/youtube/__init__.py:16` - `history = create_file_logger('history', paths.HISTORY_LOG)`

When tests imported these modules without `YRT_NO_LOGGING=1` set, file handlers were created that could write to
`_log/history.log`.

**Impact:** Test runs could pollute the production log file with test-related entries.

**Fix:** Set `YRT_NO_LOGGING=1` at the top of `conftest.py` BEFORE any yrt imports:

```python
import os

# Disable logging BEFORE importing yrt modules to prevent log file creation
os.environ['YRT_NO_LOGGING'] = '1'
```

**Note:** API calls during tests are already handled via mocking (`@patch` decorators). No real YouTube API calls are
made.

### 13. Implement main.py Tests (20 skipped)

**Location:** `_tests/test_main.py:8-141`

**Status:** Pending

**Issue:** All 20 tests for main orchestration module are marked as "Not yet implemented". Zero test coverage on
business-critical routing logic.

**Priority tests to implement:**

1. `dest_playlist()` routing logic (6 tests) - **Now covered by `test_router.py` (40 tests)**
2. Configuration loading validation (3 tests)
3. `copy_last_exe_log()` function (2 tests)
4. Exception handling (2 tests)

### 14. Extract and Test Duration Parsing

**Location:** `_tests/test_youtube.py:110-131` (3 skipped tests)

**Status:** Pending

**Issue:** Duration parsing logic is embedded in `get_stats()`, not exposed for testing. Three tests are skipped waiting
for a public utility function.

**Solution:** Create public function in `yrt/youtube/utils.py`:

```python
def parse_iso8601_duration(duration_str: str) -> int:
    """Parse ISO 8601 duration string to seconds.

    Args:
        duration_str: ISO 8601 duration (e.g., 'PT3M30S', 'PT1H30M').

    Returns:
        Total duration in seconds.

    Example:
        >>> parse_iso8601_duration('PT3M30S')
        210
    """
    return isodate.parse_duration(duration_str).total_seconds()
```

### 15. Improve archive_data.py Error Handling

**Location:** `_scripts/archive_data.py:288-295`

**Status:** Pending

**Issue:** Catches generic `Exception` instead of specific exceptions from the yrt module.

**Fix:**

```python
from yrt.exceptions import YouTubeServiceError, CredentialsError, APIError

try:
    service = create_service_local(log=False)
    sort_db(service=service, log=False)
    db_sorted = True
except (YouTubeServiceError, CredentialsError, APIError) as e:
    print(f"  Failed to sort database: {e}")
    db_sorted = False
```

---

## 🛃 Low Priority - Nice to Have

### 15. Use Generators for Memory Efficiency

**Location:** `yrt/youtube.py:537-574` (`iter_channels` function)

**Status:** Pending

**Issue:** Function accumulates all items in a list before returning, using more memory than necessary.

**Solution:** Convert to generator:

```python
def iter_channels_generator(
        service: pyt.Client,
        channels: list[str],
        day_ago: int | None = None,
        latest_d: dt.datetime = NOW,
        prog_bar: bool = True
) -> Generator[PlaylistItem, None, None]:
    """Generator that yields playlist items from channels."""
    for ch_id in channels:
        if ch_id in ADD_ON['toPass']:
            continue

        pl_id = f'UU{ch_id[2:]}'
        items = get_playlist_items(service, pl_id, day_ago, latest_d)

        for item in items:
            if playlist_item := PlaylistItem.from_api_response(item, ch_id):
                yield playlist_item
```

### 16. Add Context Manager for YouTube Service

**Status:** Pending

**Solution:**

```python
from contextlib import contextmanager
from typing import Generator


@contextmanager
def youtube_service(mode: str = 'local') -> Generator[pyt.Client, None, None]:
    """Context manager for YouTube API service."""
    if mode == 'local':
        service = create_service_local()
    else:
        service, _ = create_service_workflow()

    try:
        yield service
    finally:
        # Cleanup if needed
        pass
```

### 17. Add Exception Context Attributes

**Location:** `yrt/exceptions.py:4-30`

**Status:** Pending

**Issue:** Exceptions don't carry context information for debugging.

**Solution:**

```python
class ConfigurationError(YouTubeTrackerError):
    """Raised when there's an error with configuration files."""

    def __init__(self, message: str, file_path: str | None = None):
        super().__init__(message)
        self.file_path = file_path


class APIError(YouTubeTrackerError):
    """Raised when a YouTube API call fails."""

    def __init__(self, message: str, video_id: str | None = None, status_code: int | None = None):
        super().__init__(message)
        self.video_id = video_id
        self.status_code = status_code
```

### 18. Improve Type Hints with TypedDict/Protocol

**Status:** Pending

**Issue:** Many `# type: ignore` comments throughout codebase suggest type issues.

**Solution:** Define TypedDicts for structured data, Protocols for interfaces:

```python
from typing import TypedDict, Protocol


class PlaylistItemDict(TypedDict):
    """Type definition for playlist item dictionary."""
    video_id: str
    video_title: str
    item_id: str
    release_date: str
    status: str
    channel_id: str
    channel_name: str


class YouTubeService(Protocol):
    """Protocol for YouTube service interface."""

    def get_playlist_items(self, playlist_id: str) -> list[Any]: ...

    def get_video_info(self, video_id: str) -> Any: ...
```

### 19. Add Error Response Test Fixtures

**Location:** `_tests/fixtures/`

**Status:** Pending

**Issue:** Missing error response samples for comprehensive error handling tests.

**Missing fixtures:**

- `error_404_response.json` - Video not found
- `error_403_response.json` - Forbidden/private video
- `error_quota_exceeded.json` - Quota exceeded response
- `empty_playlist_response.json` - Empty playlist

---

## 📄 Summary

- **☢️ Critical:** 1 bug ~~requiring immediate fix~~ ✅ Fixed
- **⚠️ High Priority:** 5 structural improvements ✅ All done (Logger Factory, Split youtube.py, Domain Models,
  VideoRouter, Constants Module)
- **🛑 Medium Priority:** 5 code quality improvements
- **🧪 Test Suite:** 4 test coverage improvements (1 fixed: Test logging isolation)
- **🛃 Low Priority:** 5 nice-to-have improvements

**Total:** 20 improvement items (7 fixed, 13 remaining)

### Current Code Coverage Breakdown (43% total)

| Module                    | Coverage | Status         |
|---------------------------|----------|----------------|
| `yrt/__init__.py`         | 100%     | ✅ Complete     |
| `yrt/config.py`           | 100%     | ✅ Complete     |
| `yrt/constants.py`        | 100%     | ✅ Complete     |
| `yrt/exceptions.py`       | 100%     | ✅ Complete     |
| `yrt/logging_utils.py`    | 100%     | ✅ Complete     |
| `yrt/models.py`           | 100%     | ✅ Complete     |
| `yrt/paths.py`            | 100%     | ✅ Complete     |
| `yrt/router.py`           | 95%      | ✅ Complete     |
| `yrt/file_utils.py`       | 76%      | 🔸 Needs work  |
| `yrt/youtube/__init__.py` | 100%     | ✅ Complete     |
| `yrt/youtube/utils.py`    | 58%      | 🔸 Needs work  |
| `yrt/youtube/stats.py`    | 23%      | ⚠️ Low         |
| `yrt/youtube/api.py`      | 20%      | ⚠️ Low         |
| `yrt/youtube/auth.py`     | 17%      | ⚠️ Low         |
| `yrt/youtube/playlist.py` | 15%      | ⚠️ Low         |
| `yrt/youtube/cleanup.py`  | 12%      | ⚠️ Low         |
| `yrt/main.py`             | 0%       | ❌ Not covered  |
| `yrt/analytics.py`        | 0%       | 🚫 Placeholder |
| `yrt/_sandbox.py`         | 0%       | 🚫 Dev only    |

## Files to Modify

| File                       | Changes                            |
|----------------------------|------------------------------------|
| `yrt/file_utils.py`        | Fix logging bug, use pathlib       |
| `yrt/youtube.py`           | Split into submodules              |
| `yrt/main.py`              | Extract VideoRouter, use pathlib   |
| `yrt/config.py`            | Add validation, use logger factory |
| `yrt/paths.py`             | Keep ALLOWED_DIRS as Path objects  |
| `yrt/exceptions.py`        | Add context attributes             |
| `yrt/analytics.py`         | Remove or mark as placeholder      |
| `_scripts/archive_data.py` | Use specific exceptions            |
| `_tests/conftest.py`       | ✅ Add YRT_NO_LOGGING isolation     |
| `_tests/test_main.py`      | Implement 20 skipped tests         |
| `_tests/test_youtube.py`   | Implement duration parsing tests   |

## New Files to Create

| File                           | Purpose                  | Status                         |
|--------------------------------|--------------------------|--------------------------------|
| `yrt/logging_utils.py`         | Shared logger factory    | ✅ Created                      |
| `yrt/router.py`                | Video routing logic      | ✅ Created                      |
| `yrt/constants.py`             | Magic strings/numbers    | ✅ Created                      |
| `yrt/youtube/__init__.py`      | Package exports          | ✅ Created                      |
| `yrt/youtube/auth.py`          | Authentication functions | ✅ Created                      |
| `yrt/youtube/api.py`           | Core API calls           | ✅ Created                      |
| `yrt/youtube/stats.py`         | Statistics management    | ✅ Created                      |
| `yrt/youtube/playlist.py`      | Playlist operations      | ✅ Created                      |
| `yrt/youtube/cleanup.py`       | Cleanup operations       | ✅ Created                      |
| `yrt/youtube/models.py`        | Dataclasses and enums    | Deferred (using yrt/models.py) |
| `yrt/youtube/retry.py`         | Retry decorator          | Pending                        |
| `yrt/youtube/utils.py`         | Utilities                | ✅ Created                      |
| `_tests/test_router.py`        | Router unit tests        | ✅ Created                      |
| `_tests/test_constants.py`     | Constants unit tests     | ✅ Created                      |
| `_tests/fixtures/error_*.json` | Error response fixtures  | Pending                        |

## Implementation Order

### Phase 1: Foundation ✅ COMPLETE

**🧪 Coverage:** 43% code coverage (200 tests, 177 passing)

1. ✅ **Bug fix:** Add `YRT_NO_LOGGING` check to `yrt/file_utils.py:14-27`
2. ✅ **DRY:** Create `yrt/logging_utils.py` with shared logger factory
3. ✅ **Constants:** Create `yrt/constants.py` for magic strings/numbers
4. ✅ Add tests for new `logging_utils.py` and `constants.py` modules

### Phase 2: youtube.py Refactoring ✅ COMPLETE

**🧪 Coverage:** Maintained 43% (structural refactoring, no new coverage)

5. ✅ Create `yrt/youtube/` package structure
6. ✅ Extract `yrt/models.py` with dataclasses (PlaylistItem, VideoStats, etc.) - *Note: at package level, not youtube/*
7. ✅ Extract `yrt/youtube/auth.py` (create_service_local, create_service_workflow, encode_key)
8. ⏸️ Extract `yrt/youtube/retry.py` with retry decorator - *Deferred to Phase 5*
9. ✅ Extract `yrt/youtube/utils.py` (is_shorts, last_exe_date, sort_db, parse_iso8601_duration)
10. ✅ Extract `yrt/youtube/api.py` (get_playlist_items, get_videos, get_subs, iter_channels)
11. ✅ Extract `yrt/youtube/stats.py` (get_stats, add_stats, weekly_stats)
12. ✅ Extract `yrt/youtube/playlist.py` (add_to_playlist, del_from_playlist, fill_release_radar)
13. ✅ Extract `yrt/youtube/cleanup.py` (cleanup_expired_videos, cleanup_ended_streams)
14. ✅ Create `yrt/youtube/__init__.py` with public API exports
15. ✅ Update imports in `yrt/main.py` and `_scripts/`
16. ✅ Add/update tests for refactored youtube submodules

### Phase 3: main.py Improvements (Partial)

**🧪 Coverage target:** 55% (focus on router + config validation)

17. ✅ Extract `VideoRouter` class from `dest_playlist()` function - *Created `yrt/router.py`*
18. ⏸️ Add config validation in `yrt/config.py` - *Pending*
19. ⏸️ Use pathlib consistently in file operations - *Pending*
20. ✅ Add tests for `VideoRouter` class - *40 tests in `test_router.py`*

### Phase 4: Test Coverage Push

**🧪 Coverage target:** 75% (major push on youtube submodules)

21. Implement `dest_playlist()` routing tests (6 tests)
22. Implement configuration loading tests (3 tests)
23. Implement `copy_last_exe_log()` tests (2 tests)
24. Extract and test `parse_iso8601_duration()` function (3 tests)
25. Add integration tests for main workflow
26. Add error response test fixtures
27. Ensure all new code has comprehensive tests

### Phase 5: Cleanup & Final Polish

**🧪 Coverage target:** 90% (final goal)

28. Improve `_scripts/archive_data.py` error handling
29. Remove/mark `yrt/analytics.py` as placeholder
30. Add exception context attributes
31. Update all module docstrings and imports
32. Final test coverage audit and gap filling