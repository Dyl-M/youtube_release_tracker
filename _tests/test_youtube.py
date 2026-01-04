"""Tests for YouTube API interaction functions."""

# Standard library
from unittest.mock import Mock, patch

# Third-party
import pytest

# Local - explicit imports from submodules
from yrt.youtube.utils import (
    is_shorts,
    ISO_DATE_FORMAT,
    TRANSIENT_ERRORS,
    PERMANENT_ERRORS,
    QUOTA_ERRORS,
)
from yrt.youtube.auth import (
    encode_key,
    create_service_local,
    create_service_workflow,
)
from yrt.youtube.stats import get_stats


@pytest.mark.unit
@pytest.mark.api
class TestIsShorts:
    """Test is_shorts() function for YouTube Shorts detection."""

    @patch('yrt.youtube.utils.requests.head')
    def test_is_shorts_returns_true_for_shorts(self, mock_head, sample_video_id):
        """Test is_shorts() returns True for actual shorts (200 status)."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_head.return_value = mock_response

        result = is_shorts(sample_video_id)

        assert result is True
        mock_head.assert_called_once()
        # Verify allow_redirects=False is used (critical for correct detection)
        call_kwargs = mock_head.call_args.kwargs
        assert call_kwargs.get('allow_redirects') is False

    @patch('yrt.youtube.utils.requests.head')
    def test_is_shorts_returns_false_for_regular_videos(self, mock_head, sample_video_id):
        """Test is_shorts() returns False for regular videos (3xx redirect)."""
        mock_response = Mock()
        mock_response.status_code = 301  # Redirect
        mock_head.return_value = mock_response

        result = is_shorts(sample_video_id)

        assert result is False

    @patch('yrt.youtube.utils.requests.head')
    def test_is_shorts_has_timeout(self, mock_head, sample_video_id):
        """Test is_shorts() uses timeout to prevent hanging."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_head.return_value = mock_response

        is_shorts(sample_video_id)

        call_kwargs = mock_head.call_args.kwargs
        assert 'timeout' in call_kwargs
        assert call_kwargs['timeout'] > 0

    @patch('yrt.youtube.utils.requests.head')
    def test_is_shorts_handles_network_error(self, mock_head, sample_video_id):
        """Test is_shorts() returns False on network errors."""
        mock_head.side_effect = Exception("Network error")

        result = is_shorts(sample_video_id)

        # Should return False as safe default
        assert result is False


@pytest.mark.unit
class TestErrorConstants:
    """Test error categorization constants."""

    @staticmethod
    def test_transient_errors_defined():
        """Test TRANSIENT_ERRORS constant is defined with normalized lowercase values."""
        assert isinstance(TRANSIENT_ERRORS, set)
        assert 'serviceunavailable' in TRANSIENT_ERRORS
        assert 'backenderror' in TRANSIENT_ERRORS
        assert 'internalerror' in TRANSIENT_ERRORS

    @staticmethod
    def test_permanent_errors_defined():
        """Test PERMANENT_ERRORS constant is defined with normalized lowercase values."""
        assert isinstance(PERMANENT_ERRORS, set)
        assert 'videonotfound' in PERMANENT_ERRORS
        assert 'forbidden' in PERMANENT_ERRORS
        assert 'duplicate' in PERMANENT_ERRORS

    @staticmethod
    def test_quota_errors_defined():
        """Test QUOTA_ERRORS constant is defined with normalized lowercase values."""
        assert isinstance(QUOTA_ERRORS, set)
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
    """Test ISO 8601 duration parsing."""

    @staticmethod
    @pytest.mark.skip("Not yet implemented")
    def test_parse_short_duration():
        """Test parsing short video duration (< 1 minute)."""
        # PT30S = 30 seconds
        # This test assumes a helper function exists or we test via get_stats
        # If no helper exists, this documents expected behavior

    @staticmethod
    @pytest.mark.skip("Not yet implemented")
    def test_parse_medium_duration():
        """Test parsing medium video duration (minutes)."""
        # PT3M30S = 3 minutes 30 seconds

    @staticmethod
    @pytest.mark.skip("Not yet implemented")
    def test_parse_long_duration():
        """Test parsing long video duration (hours)."""
        # PT1H30M = 1 hour 30 minutes


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
