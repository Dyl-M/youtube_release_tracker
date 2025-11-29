# Test Suite for YouTube Release Tracker

Comprehensive test suite using pytest for the YouTube Release Tracker project.

## Structure

```
_tests/
├── conftest.py              # Shared fixtures and pytest configuration
├── fixtures/                # Sample data files for testing
├── test_exceptions.py       # Tests for custom exception hierarchy
├── test_file_utils.py       # Tests for file operations
├── test_main.py             # Tests for main orchestration logic
├── test_paths.py            # Tests for centralized path definitions
├── test_youtube.py          # Tests for YouTube API functions
└── README.md                # This file
```

## Running Tests

### Run all tests
```bash
pytest
```

### Run specific test file
```bash
pytest _tests/test_youtube.py
```

### Run tests by marker
```bash
# Run only unit tests
pytest -m unit

# Run only API tests
pytest -m api

# Run integration tests
pytest -m integration

# Skip slow tests
pytest -m "not slow"
```

### Run with coverage
```bash
pytest --cov=yrt --cov-report=html --cov-report=term-missing
```

### Run with verbose output
```bash
pytest -v
```

### Run specific test
```bash
pytest _tests/test_youtube.py::TestIsShorts::test_is_shorts_returns_true_for_shorts
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

## Test Coverage Goals

Current implementation tests:

1. **Exception Hierarchy** (test_exceptions.py)
   - All custom exceptions
   - Inheritance relationships
   - Exception catching behavior

2. **Path Management** (test_paths.py)
   - Path constants existence
   - Directory structure
   - Absolute paths
   - Path validation lists

3. **File Operations** (test_file_utils.py)
   - JSON loading and saving
   - Required key validation
   - Nested key validation
   - Error handling

4. **YouTube API** (test_youtube.py)
   - Shorts detection (is_shorts)
   - Error categorization constants
   - Retry mechanism configuration
   - Service creation functions

5. **Main Logic** (test_main.py)
   - Video routing (dest_playlist)
   - Configuration loading
   - Main orchestration
   - Workflow modes

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
- All project dependencies from requirements.txt

Install test dependencies:
```bash
pip install pytest pytest-cov
```

## Continuous Integration

Tests should be run in CI/CD pipeline before deployment to ensure code quality and prevent regressions.

## Notes

- Tests use mocking extensively to avoid actual API calls
- Temporary directories (`tmp_path` fixture) are automatically cleaned up
- All file operations in tests use temporary paths
- Network operations are mocked to ensure tests run offline
