"""Tests for YouTube API interaction functions."""

# Standard library
from unittest.mock import Mock, patch

# Third-party
import pytest

# Local
from yrt.youtube.auth import (
    create_service_local,
    create_service_workflow,
    encode_key,
)
from yrt.youtube.stats import get_stats
from yrt.youtube.utils import (
    ISO_DATE_FORMAT,
    PERMANENT_ERRORS,
    QUOTA_ERRORS,
    TRANSIENT_ERRORS,
    is_shorts,
    parse_iso8601_duration,
)


@pytest.mark.unit
@pytest.mark.api
class TestIsShorts:
    """Test is_shorts() function for YouTube Shorts detection."""

    @staticmethod
    def test_is_shorts_returns_true_for_shorts(sample_video_id):
        """Test is_shorts() returns True for actual shorts (200 status)."""
        mock_response = Mock()
        mock_response.status_code = 200

        with patch('yrt.youtube.utils.requests.head', return_value=mock_response) as mock_head:
            result = is_shorts(sample_video_id)

        assert result is True
        mock_head.assert_called_once()
        # Verify allow_redirects=False is used (critical for correct detection)
        call_kwargs = mock_head.call_args.kwargs
        assert call_kwargs.get('allow_redirects') is False

    @staticmethod
    def test_is_shorts_returns_false_for_regular_videos(sample_video_id):
        """Test is_shorts() returns False for regular videos (3xx redirect)."""
        mock_response = Mock()
        mock_response.status_code = 301  # Redirect

        with patch('yrt.youtube.utils.requests.head', return_value=mock_response):
            result = is_shorts(sample_video_id)

        assert result is False

    @staticmethod
    def test_is_shorts_has_timeout(sample_video_id):
        """Test is_shorts() uses timeout to prevent hanging."""
        mock_response = Mock()
        mock_response.status_code = 200

        with patch('yrt.youtube.utils.requests.head', return_value=mock_response) as mock_head:
            is_shorts(sample_video_id)

        call_kwargs = mock_head.call_args.kwargs
        assert 'timeout' in call_kwargs
        assert call_kwargs['timeout'] > 0

    @staticmethod
    def test_is_shorts_handles_network_error(sample_video_id):
        """Test is_shorts() returns False on network errors."""
        with patch('yrt.youtube.utils.requests.head', side_effect=Exception('Network error')):
            result = is_shorts(sample_video_id)

        # Should return False as safe default
        assert result is False


@pytest.mark.unit
class TestErrorConstants:
    """Test error categorization constants."""

    @staticmethod
    def test_transient_errors_defined():
        """Test TRANSIENT_ERRORS constant is defined with normalized lowercase values."""
        assert isinstance(TRANSIENT_ERRORS, (set, frozenset))
        assert 'serviceunavailable' in TRANSIENT_ERRORS
        assert 'backenderror' in TRANSIENT_ERRORS
        assert 'internalerror' in TRANSIENT_ERRORS

    @staticmethod
    def test_permanent_errors_defined():
        """Test PERMANENT_ERRORS constant is defined with normalized lowercase values."""
        assert isinstance(PERMANENT_ERRORS, (set, frozenset))
        assert 'videonotfound' in PERMANENT_ERRORS
        assert 'forbidden' in PERMANENT_ERRORS
        assert 'duplicate' in PERMANENT_ERRORS

    @staticmethod
    def test_quota_errors_defined():
        """Test QUOTA_ERRORS constant is defined with normalized lowercase values."""
        assert isinstance(QUOTA_ERRORS, (set, frozenset))
        assert 'quotaexceeded' in QUOTA_ERRORS

    @staticmethod
    def test_retry_constants_defined():
        """Test retry configuration constants are defined in config module."""
        from yrt import config

        assert hasattr(config, 'MAX_RETRIES')
        assert hasattr(config, 'BASE_DELAY')
        assert hasattr(config, 'MAX_BACKOFF')
        assert config.MAX_RETRIES >= 3
        assert config.BASE_DELAY >= 1
        assert config.MAX_BACKOFF >= config.BASE_DELAY


@pytest.mark.unit
class TestDurationParsing:
    """Test ISO 8601 duration parsing (parse_iso8601_duration)."""

    @staticmethod
    def test_parse_short_duration():
        """Test parsing short video duration (< 1 minute)."""
        assert parse_iso8601_duration('PT30S') == 30

    @staticmethod
    def test_parse_medium_duration():
        """Test parsing medium video duration (minutes)."""
        assert parse_iso8601_duration('PT3M30S') == 210

    @staticmethod
    def test_parse_long_duration():
        """Test parsing long video duration (hours)."""
        assert parse_iso8601_duration('PT1H30M') == 5400

    @staticmethod
    def test_parse_duration_over_a_day_keeps_days():
        """Test durations of a day or more keep their days (regression: timedelta.seconds dropped them)."""
        assert parse_iso8601_duration('P1DT1H') == 90000

    @staticmethod
    def test_parse_missing_duration_is_zero():
        """Test None and empty strings (unknown duration) map to 0 seconds."""
        assert parse_iso8601_duration(None) == 0
        assert parse_iso8601_duration('') == 0

    @staticmethod
    def test_parse_invalid_duration_is_zero_with_warning(history_mock):
        """Test an unparseable duration maps to 0 seconds and is logged instead of aborting."""
        assert parse_iso8601_duration('garbage') == 0
        assert history_mock.warning.call_count == 1


@pytest.mark.unit
@pytest.mark.api
class TestGetStats:
    """Test get_stats() function."""

    @staticmethod
    def test_get_stats_has_check_shorts_parameter():
        """Test get_stats() accepts check_shorts parameter."""
        import inspect

        sig = inspect.signature(get_stats)
        assert 'check_shorts' in sig.parameters

    @staticmethod
    def test_get_stats_check_shorts_default_true():
        """Test check_shorts defaults to True for new videos."""
        import inspect

        sig = inspect.signature(get_stats)
        param = sig.parameters['check_shorts']
        assert param.default is True


@pytest.mark.unit
class TestDateFormatting:
    """Test date and time formatting constants."""

    @staticmethod
    def test_iso_date_format_constant():
        """Test ISO_DATE_FORMAT constant is defined."""
        assert isinstance(ISO_DATE_FORMAT, str)
        assert 'Y' in ISO_DATE_FORMAT
        assert 'm' in ISO_DATE_FORMAT
        assert 'd' in ISO_DATE_FORMAT


@pytest.mark.integration
@pytest.mark.slow
class TestServiceCreation:
    """Test YouTube API service creation functions."""

    @staticmethod
    def test_create_service_local_function_exists():
        """Test create_service_local() function exists."""
        assert callable(create_service_local)

    @staticmethod
    def test_create_service_workflow_function_exists():
        """Test create_service_workflow() function exists."""
        assert callable(create_service_workflow)


@pytest.mark.unit
class TestHelperFunctions:
    """Test helper and utility functions."""

    @staticmethod
    def test_encode_key_function_exists():
        """Test encode_key() function exists for base64 encoding."""
        assert callable(encode_key)
