# -*- coding: utf-8 -*-

import pytest

from yrt.exceptions import (
    YouTubeTrackerError,
    ConfigurationError,
    FileAccessError,
    YouTubeServiceError,
    CredentialsError,
    APIError
)

"""Tests for custom exception hierarchy."""


@pytest.mark.unit
class TestExceptionHierarchy:
    """Test custom exception class hierarchy."""

    def test_base_exception(self):
        """Test YouTubeTrackerError base exception."""
        error = YouTubeTrackerError("Base error message")
        assert str(error) == "Base error message"
        assert isinstance(error, Exception)

    def test_configuration_error(self):
        """Test ConfigurationError inherits from base."""
        error = ConfigurationError("Config error")
        assert isinstance(error, YouTubeTrackerError)
        assert str(error) == "Config error"

    def test_file_access_error(self):
        """Test FileAccessError inherits from base."""
        error = FileAccessError("File access denied")
        assert isinstance(error, YouTubeTrackerError)
        assert str(error) == "File access denied"

    def test_youtube_service_error(self):
        """Test YouTubeServiceError inherits from base."""
        error = YouTubeServiceError("Service creation failed")
        assert isinstance(error, YouTubeTrackerError)
        assert str(error) == "Service creation failed"

    def test_credentials_error(self):
        """Test CredentialsError inherits from base."""
        error = CredentialsError("Invalid credentials")
        assert isinstance(error, YouTubeTrackerError)
        assert str(error) == "Invalid credentials"

    def test_api_error(self):
        """Test APIError inherits from base."""
        error = APIError("API call failed")
        assert isinstance(error, YouTubeTrackerError)
        assert str(error) == "API call failed"

    def test_exception_catching(self):
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
