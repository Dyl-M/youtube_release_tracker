"""Custom exceptions for the YouTube Release Tracker application."""


class YouTubeTrackerError(Exception):
    """Base exception for all YouTube Release Tracker errors."""


class ConfigurationError(YouTubeTrackerError):
    """Raised when there's an error with configuration files (missing, malformed, invalid keys)."""


class FileAccessError(YouTubeTrackerError):
    """Raised when file access is denied (path traversal, invalid extension, etc.)."""


class YouTubeServiceError(YouTubeTrackerError):
    """Raised when YouTube API service creation or operations fail."""


class CredentialsError(YouTubeTrackerError):
    """Raised when there's an issue with authentication credentials."""


class APIError(YouTubeTrackerError):
    """Raised when YouTube API calls fail with unrecoverable errors."""


class GitHubError(YouTubeTrackerError):
    """Raised when GitHub API operations fail (secrets update, repository access, etc.)."""
