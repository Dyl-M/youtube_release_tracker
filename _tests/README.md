# Test Suite for YouTube Release Tracker

Comprehensive test suite using pytest for the YouTube Release Tracker project.

## Structure

```
_tests/
├── conftest.py              # Shared fixtures and pytest configuration
├── fixtures/                # Sample data files for testing
│   ├── empty_playlist_response.json
│   ├── error_403_response.json      # forbidden (permanent)
│   ├── error_404_response.json      # playlistNotFound
│   ├── error_503_backend.json       # backendError (transient)
│   ├── error_quota_exceeded.json    # quotaExceeded
│   ├── sample_playlist_response.json
│   └── sample_video_stats.json
├── test_api.py              # Tests for core API calls through the retry layer
├── test_cleanup.py          # Tests for retention / ended-stream cleanup
├── test_config.py           # Tests for centralized configuration and validation
├── test_exceptions.py       # Tests for custom exception hierarchy and context
├── test_file_utils.py       # Tests for file operations and validation
├── test_logging_utils.py    # Tests for logger factory
├── test_main.py             # Tests for main orchestration logic
├── test_models.py           # Tests for domain models/dataclasses
├── test_paths.py            # Tests for centralized path definitions
├── test_playlist.py         # Tests for playlist writes and api_failure.json bookkeeping
├── test_quota.py            # Tests for the quota tracker
├── test_retry.py            # Tests for retry, error triage and quota charging
├── test_smoke_flow.py       # Zero-quota integration flow of the daily job's steps
├── test_youtube.py          # Tests for YouTube API functions
└── README.md                # This file
```

## Running Tests

**Important:** This project uses `uv` as the package manager. Always use `uv run` to execute pytest commands.

### Run all tests

```bash
uv run pytest _tests/ -v
```

### Run specific test file

```bash
uv run pytest _tests/test_youtube.py -v
uv run pytest _tests/test_models.py -v
```

### Run tests by marker

```bash
# Run only unit tests
uv run pytest _tests/ -m unit -v

# Run only API tests
uv run pytest _tests/ -m api -v

# Run integration tests
uv run pytest _tests/ -m integration -v

# Skip slow tests
uv run pytest _tests/ -m "not slow" -v
```

### Run with coverage

```bash
uv run pytest _tests/ --cov=yrt --cov-report=html --cov-report=term-missing
```

### Run with verbose output

```bash
uv run pytest _tests/ -v
```

### Run specific test

```bash
uv run pytest _tests/test_youtube.py::TestIsShorts::test_is_shorts_returns_true_for_shorts -v
uv run pytest _tests/test_models.py::test_playlist_config_creation -v
```

## Test Markers

- `@pytest.mark.unit` - Unit tests for individual functions
- `@pytest.mark.integration` - Integration tests for module interactions
- `@pytest.mark.api` - Tests requiring API mocking
- `@pytest.mark.slow` - Tests that take significant time to run

## Fixtures

Common fixtures are defined in `conftest.py`:

- `sample_video_id` - Sample YouTube video ID
- `sample_channel_id` - Sample YouTube channel ID
- `sample_playlist_id` - Sample YouTube playlist ID
- `sample_datetime` - Sample datetime with timezone
- `sample_video_data` - Sample video metadata
- `sample_playlist_item` - Sample playlist item from API
- `sample_video_stats` - Sample video statistics
- `mock_youtube_client` - Mock pyyoutube Client
- `sample_pocket_tube_data` - Sample pocket_tube.json config
- `sample_playlists_data` - Sample playlists.json config
- `sample_addon_data` - Sample add-on.json config
- `temp_json_file` - Helper to create temporary JSON files
- `mock_requests_response` - Mock requests response
- `api_error(fixture_name)` - Factory building a real `PyYouTubeException` from a JSON error fixture
- `no_sleep` - Patches the retry layer's `time.sleep` (yields the mock)
- `quota_tracker` - Installs a small deterministic `QuotaTracker` as the process-wide default
- `history_mock` - Replaces the shared youtube logger with a `MagicMock`
- `_reset_quota_tracker` - Autouse: drops the process-wide tracker after each test

## Test Coverage Goals

Current implementation tests:

1. **Configuration** (test_config.py) - 22 tests ✅
    - Deep merge functionality
    - Constants loading with defaults
    - Partial config overrides
    - All configuration constants validation

2. **Exception Hierarchy** (test_exceptions.py) - 7 tests ✅
    - All custom exceptions
    - Inheritance relationships
    - Exception catching behavior

3. **File Operations** (test_file_utils.py) - 13 tests ✅
    - JSON loading and saving
    - Required key validation (flat and nested)
    - Path validation security
    - Error handling

4. **Logging Utilities** (test_logging_utils.py) - 10 tests ✅
    - Logger factory creation
    - File handler configuration
    - YRT_NO_LOGGING environment variable
    - Multiple independent loggers

5. **Main Logic** (test_main.py) - 0/20 tests ⏭️
    - Video routing (dest_playlist) - skipped
    - Configuration loading - skipped
    - Main orchestration - skipped
    - Workflow modes - skipped

6. **Domain Models** (test_models.py) - 26 tests ✅ NEW
    - PlaylistConfig validation (5 tests)
    - AddOnConfig validation (3 tests)
    - PlaylistItem validation (3 tests)
    - VideoStats validation (3 tests)
    - VideoData factory method (3 tests)
    - PlaylistItemRef validation (4 tests)
    - Helper functions to_dict/to_dict_list (5 tests)

7. **Path Management** (test_paths.py) - 8 tests ✅
    - Path constants existence
    - Directory structure
    - Absolute paths
    - Path validation lists

8. **YouTube API** (test_youtube.py) - 14/17 tests
    - Shorts detection (is_shorts) ✅
    - Error categorization constants ✅
    - Retry mechanism configuration ✅
    - Service creation functions ✅
    - Duration parsing - skipped (3 tests)

9. **Retry layer / quota** (test_retry.py, test_quota.py) ✅
    - Reason normalisation and extraction, classification, backoff bounds
    - `call_api` semantics: retried / skipped / saved, charging rules, `MAX_RETRIES = 0`
    - `QuotaTracker` arithmetic, summary line, process-wide default

10. **API, playlist, cleanup** (test_api.py, test_playlist.py, test_cleanup.py) ✅
    - 404 handling, transient retry, error re-wrapping with context
    - `add_to_playlist` triage and `api_failure.json` bookkeeping, deletes, `add_api_fail`
    - Retention filtering, partial results on quota, ended-stream detection

11. **Smoke flow** (test_smoke_flow.py) ✅ - the daily job's steps end to end against the mock client

**Total:** 313 tests | **Passing:** 293 | **Skipped:** 20 | **Line coverage:** 69%

## Adding New Tests

1. Create or update test file in `_tests/`
2. Use appropriate markers (`@pytest.mark.unit`, etc.)
3. Add fixtures to `conftest.py` if reusable
4. Follow naming convention: `test_<functionality>.py`
5. Use descriptive test function names: `test_<what>_<expected_behavior>`
6. Include docstrings explaining what is being tested

## Dependencies

Tests require:

- pytest
- pytest-cov (for coverage reports)
- All project dependencies from `pyproject.toml`

Install test dependencies:

```bash
# Install all dependencies including dev extras
uv sync --extra dev
```

## Continuous Integration

Tests should be run in CI/CD pipeline before deployment to ensure code quality and prevent regressions.

## Notes

- Tests use mocking extensively to avoid actual API calls
- Temporary directories (`tmp_path` fixture) are automatically cleaned up
- All file operations in tests use temporary paths
- Network operations are mocked to ensure tests run offline
