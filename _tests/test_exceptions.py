"""Tests for custom exception hierarchy."""

# Third-party
import pytest

# Local
from yrt.exceptions import (
    APIError,
    ConfigurationError,
    CredentialsError,
    ErrorCategory,
    FileAccessError,
    QuotaExhaustedError,
    YouTubeServiceError,
    YouTubeTrackerError,
)


@pytest.mark.unit
class TestExceptionHierarchy:
    """Test custom exception class hierarchy."""

    @staticmethod
    def test_base_exception():
        """Test YouTubeTrackerError base exception."""
        error = YouTubeTrackerError('Base error message')
        assert str(error) == 'Base error message'
        assert isinstance(error, Exception)

    @staticmethod
    def test_configuration_error():
        """Test ConfigurationError inherits from base."""
        error = ConfigurationError('Config error')
        assert isinstance(error, YouTubeTrackerError)
        assert str(error) == 'Config error'

    @staticmethod
    def test_file_access_error():
        """Test FileAccessError inherits from base."""
        error = FileAccessError('File access denied')
        assert isinstance(error, YouTubeTrackerError)
        assert str(error) == 'File access denied'

    @staticmethod
    def test_youtube_service_error():
        """Test YouTubeServiceError inherits from base."""
        error = YouTubeServiceError('Service creation failed')
        assert isinstance(error, YouTubeTrackerError)
        assert str(error) == 'Service creation failed'

    @staticmethod
    def test_credentials_error():
        """Test CredentialsError inherits from base."""
        error = CredentialsError('Invalid credentials')
        assert isinstance(error, YouTubeTrackerError)
        assert str(error) == 'Invalid credentials'

    @staticmethod
    def test_api_error():
        """Test APIError inherits from base."""
        error = APIError('API call failed')
        assert isinstance(error, YouTubeTrackerError)
        assert str(error) == 'API call failed'

    @staticmethod
    def test_exception_catching():
        """Test that all custom exceptions can be caught by base class."""
        exceptions = [
            ConfigurationError('test'),
            FileAccessError('test'),
            YouTubeServiceError('test'),
            CredentialsError('test'),
            APIError('test'),
            QuotaExhaustedError('test'),
        ]

        for exc in exceptions:
            with pytest.raises(YouTubeTrackerError):
                raise exc


@pytest.mark.unit
class TestExceptionContext:
    """Test the context attributes carried by APIError, QuotaExhaustedError and ConfigurationError."""

    @staticmethod
    def test_api_error_context_defaults_to_none():
        """Test APIError built with a message only has empty context."""
        error = APIError('API call failed')
        assert error.reason is None
        assert error.status_code is None
        assert error.video_id is None
        assert error.category is None

    @staticmethod
    def test_api_error_carries_context():
        """Test APIError keeps reason, status code, video ID and category."""
        error = APIError(
            'Insert failed',
            reason='forbidden',
            status_code=403,
            video_id='dQw4w9WgXcQ',
            category=ErrorCategory.PERMANENT,
        )
        assert str(error) == 'Insert failed'
        assert error.reason == 'forbidden'
        assert error.status_code == 403
        assert error.video_id == 'dQw4w9WgXcQ'
        assert error.category is ErrorCategory.PERMANENT

    @staticmethod
    def test_api_error_context_is_keyword_only():
        """Test context attributes cannot be passed positionally (guards call-site mistakes)."""
        with pytest.raises(TypeError):
            APIError('Insert failed', 'forbidden')  # type: ignore[misc]

    @staticmethod
    def test_quota_exhausted_error_is_api_error_with_quota_category():
        """Test QuotaExhaustedError is an APIError whose category is always QUOTA."""
        error = QuotaExhaustedError('Quota exceeded')
        assert isinstance(error, APIError)
        assert error.category is ErrorCategory.QUOTA
        assert error.reason == 'quotaexceeded'
        assert error.status_code == 403
        assert error.video_id is None

    @staticmethod
    def test_quota_exhausted_error_keeps_video_id():
        """Test QuotaExhaustedError carries the video the failing call was about."""
        error = QuotaExhaustedError('Quota exceeded', video_id='dQw4w9WgXcQ')
        assert error.video_id == 'dQw4w9WgXcQ'

    @staticmethod
    def test_configuration_error_file_path():
        """Test ConfigurationError optionally records the offending file path."""
        assert ConfigurationError('bad config').file_path is None
        assert (
            ConfigurationError('bad config', file_path='_config/constants.json').file_path == '_config/constants.json'
        )

    @staticmethod
    def test_error_category_values():
        """Test ErrorCategory exposes the four triage outcomes with stable string values."""
        assert {category.value for category in ErrorCategory} == {'transient', 'permanent', 'quota', 'unknown'}
