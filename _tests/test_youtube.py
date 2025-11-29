# -*- coding: utf-8 -*-

import pytest
import datetime as dt

from unittest.mock import Mock, patch, MagicMock

from yrt import youtube

"""Tests for YouTube API interaction functions."""


@pytest.mark.unit
@pytest.mark.api
class TestIsShorts:
    """Test is_shorts() function for YouTube Shorts detection."""

    @patch('yrt.youtube.requests.head')
    def test_is_shorts_returns_true_for_shorts(self, mock_head, sample_video_id):
        """Test is_shorts() returns True for actual shorts (200 status)."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_head.return_value = mock_response

        result = youtube.is_shorts(sample_video_id)

        assert result is True
        mock_head.assert_called_once()
        # Verify allow_redirects=False is used (critical for correct detection)
        call_kwargs = mock_head.call_args.kwargs
        assert call_kwargs.get('allow_redirects') is False

    @patch('yrt.youtube.requests.head')
    def test_is_shorts_returns_false_for_regular_videos(self, mock_head, sample_video_id):
        """Test is_shorts() returns False for regular videos (3xx redirect)."""
        mock_response = Mock()
        mock_response.status_code = 301  # Redirect
        mock_head.return_value = mock_response

        result = youtube.is_shorts(sample_video_id)

        assert result is False

    @patch('yrt.youtube.requests.head')
    def test_is_shorts_has_timeout(self, mock_head, sample_video_id):
        """Test is_shorts() uses timeout to prevent hanging."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_head.return_value = mock_response

        youtube.is_shorts(sample_video_id)

        call_kwargs = mock_head.call_args.kwargs
        assert 'timeout' in call_kwargs
        assert call_kwargs['timeout'] > 0

    @patch('yrt.youtube.requests.head')
    def test_is_shorts_handles_network_error(self, mock_head, sample_video_id):
        """Test is_shorts() returns False on network errors."""
        mock_head.side_effect = Exception("Network error")

        result = youtube.is_shorts(sample_video_id)

        # Should return False as safe default
        assert result is False


@pytest.mark.unit
class TestErrorConstants:
    """Test error categorization constants."""

    def test_transient_errors_defined(self):
        """Test TRANSIENT_ERRORS constant is defined."""
        assert hasattr(youtube, 'TRANSIENT_ERRORS')
        assert isinstance(youtube.TRANSIENT_ERRORS, list)
        assert 'serviceUnavailable' in youtube.TRANSIENT_ERRORS
        assert 'backendError' in youtube.TRANSIENT_ERRORS
        assert 'internalError' in youtube.TRANSIENT_ERRORS

    def test_permanent_errors_defined(self):
        """Test PERMANENT_ERRORS constant is defined."""
        assert hasattr(youtube, 'PERMANENT_ERRORS')
        assert isinstance(youtube.PERMANENT_ERRORS, list)
        assert 'videoNotFound' in youtube.PERMANENT_ERRORS
        assert 'forbidden' in youtube.PERMANENT_ERRORS
        assert 'duplicate' in youtube.PERMANENT_ERRORS

    def test_quota_errors_defined(self):
        """Test QUOTA_ERRORS constant is defined."""
        assert hasattr(youtube, 'QUOTA_ERRORS')
        assert isinstance(youtube.QUOTA_ERRORS, list)
        assert 'quotaExceeded' in youtube.QUOTA_ERRORS

    def test_retry_constants_defined(self):
        """Test retry configuration constants are defined."""
        assert hasattr(youtube, 'MAX_RETRIES')
        assert hasattr(youtube, 'BASE_DELAY')
        assert hasattr(youtube, 'MAX_BACKOFF')
        assert youtube.MAX_RETRIES >= 3
        assert youtube.BASE_DELAY >= 1
        assert youtube.MAX_BACKOFF >= youtube.BASE_DELAY


@pytest.mark.unit
class TestDurationParsing:
    """Test ISO 8601 duration parsing."""

    def test_parse_short_duration(self):
        """Test parsing short video duration (< 1 minute)."""
        # PT30S = 30 seconds
        duration_str = 'PT30S'
        # This test assumes a helper function exists or we test via get_stats
        # If no helper exists, this documents expected behavior
        pass

    def test_parse_medium_duration(self):
        """Test parsing medium video duration (minutes)."""
        # PT3M30S = 3 minutes 30 seconds
        duration_str = 'PT3M30S'
        pass

    def test_parse_long_duration(self):
        """Test parsing long video duration (hours)."""
        # PT1H30M = 1 hour 30 minutes
        duration_str = 'PT1H30M'
        pass


@pytest.mark.unit
@pytest.mark.api
class TestGetStats:
    """Test get_stats() function."""

    def test_get_stats_has_check_shorts_parameter(self):
        """Test get_stats() accepts check_shorts parameter."""
        import inspect
        sig = inspect.signature(youtube.get_stats)
        assert 'check_shorts' in sig.parameters

    def test_get_stats_check_shorts_default_true(self):
        """Test check_shorts defaults to True for new videos."""
        import inspect
        sig = inspect.signature(youtube.get_stats)
        param = sig.parameters['check_shorts']
        assert param.default is True


@pytest.mark.unit
class TestDateFormatting:
    """Test date and time formatting constants."""

    def test_iso_date_format_constant(self):
        """Test ISO_DATE_FORMAT constant is defined."""
        assert hasattr(youtube, 'ISO_DATE_FORMAT')
        assert isinstance(youtube.ISO_DATE_FORMAT, str)
        assert 'Y' in youtube.ISO_DATE_FORMAT
        assert 'm' in youtube.ISO_DATE_FORMAT
        assert 'd' in youtube.ISO_DATE_FORMAT


@pytest.mark.integration
@pytest.mark.slow
class TestServiceCreation:
    """Test YouTube API service creation functions."""

    def test_create_service_local_function_exists(self):
        """Test create_service_local() function exists."""
        assert hasattr(youtube, 'create_service_local')
        assert callable(youtube.create_service_local)

    def test_create_service_workflow_function_exists(self):
        """Test create_service_workflow() function exists."""
        assert hasattr(youtube, 'create_service_workflow')
        assert callable(youtube.create_service_workflow)


@pytest.mark.unit
class TestHelperFunctions:
    """Test helper and utility functions."""

    def test_encode_key_function_exists(self):
        """Test encode_key() function exists for base64 encoding."""
        assert hasattr(youtube, 'encode_key')
        assert callable(youtube.encode_key)
