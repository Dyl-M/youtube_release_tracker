"""Tests for custom exception hierarchy."""

# Third-party
import pytest

# Local
from yrt.exceptions import (
    YouTubeTrackerError,
    ConfigurationError,
    FileAccessError,
    YouTubeServiceError,
    CredentialsError,
    APIError
)


@pytest.mark.unit
class TestExceptionHierarchy:
    """Test custom exception class hierarchy."""

    @staticmethod
    def test_base_exception():
        """Test YouTubeTrackerError base exception."""
        error = YouTubeTrackerError("Base error message")
        assert str(error) == "Base error message"
        assert isinstance(error, Exception)

    @staticmethod
    def test_configuration_error():
        """Test ConfigurationError inherits from base."""
        error = ConfigurationError("Config error")
        assert isinstance(error, YouTubeTrackerError)
        assert str(error) == "Config error"

    @staticmethod
    def test_file_access_error():
        """Test FileAccessError inherits from base."""
        error = FileAccessError("File access denied")
        assert isinstance(error, YouTubeTrackerError)
        assert str(error) == "File access denied"

    @staticmethod
    def test_youtube_service_error():
        """Test YouTubeServiceError inherits from base."""
        error = YouTubeServiceError("Service creation failed")
        assert isinstance(error, YouTubeTrackerError)
        assert str(error) == "Service creation failed"

    @staticmethod
    def test_credentials_error():
        """Test CredentialsError inherits from base."""
        error = CredentialsError("Invalid credentials")
        assert isinstance(error, YouTubeTrackerError)
        assert str(error) == "Invalid credentials"

    @staticmethod
    def test_api_error():
        """Test APIError inherits from base."""
        error = APIError("API call failed")
        assert isinstance(error, YouTubeTrackerError)
        assert str(error) == "API call failed"

    @staticmethod
    def test_exception_catching():
        """Test that all custom exceptions can be caught by base class."""
        exceptions = [
            ConfigurationError("test"),
            FileAccessError("test"),
            YouTubeServiceError("test"),
            CredentialsError("test"),
            APIError("test")
        ]

        for exc in exceptions:
            with pytest.raises(YouTubeTrackerError):
                raise exc
