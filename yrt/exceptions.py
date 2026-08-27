"""Custom exceptions for the YouTube Release Tracker application."""

# Standard library
import enum


class ErrorCategory(enum.Enum):
    """Category of a YouTube API failure, driving retry and persistence decisions.

    TRANSIENT errors are retried with backoff, PERMANENT errors are logged and skipped, QUOTA errors are saved for a
    later run, and UNKNOWN errors are treated like quota errors (saved) because the safe default is to try again later.
    """

    TRANSIENT = 'transient'
    PERMANENT = 'permanent'
    QUOTA = 'quota'
    UNKNOWN = 'unknown'


class YouTubeTrackerError(Exception):
    """Base exception for all YouTube Release Tracker errors."""


class ConfigurationError(YouTubeTrackerError):
    """Raised when there's an error with configuration files (missing, malformed, invalid keys)."""

    def __init__(self, message: str, *, file_path: str | None = None) -> None:
        """Initialize the error with an optional offending file path.

        Args:
            message: Human-readable description of the problem.
            file_path: Path of the configuration file involved, if any.
        """
        super().__init__(message)
        self.file_path = file_path


class FileAccessError(YouTubeTrackerError):
    """Raised when file access is denied (path traversal, invalid extension, etc.)."""


class YouTubeServiceError(YouTubeTrackerError):
    """Raised when YouTube API service creation or operations fail."""


class CredentialsError(YouTubeTrackerError):
    """Raised when there's an issue with authentication credentials."""


class APIError(YouTubeTrackerError):
    """Raised when YouTube API calls fail with unrecoverable errors."""

    def __init__(
        self,
        message: str,
        *,
        reason: str | None = None,
        status_code: int | None = None,
        video_id: str | None = None,
        category: ErrorCategory | None = None,
    ) -> None:
        """Initialize the error with the context extracted from the API response.

        Args:
            message: Human-readable description of the failure.
            reason: Normalized API error reason (e.g. 'quotaexceeded'), if known.
            status_code: HTTP status code returned by the API, if known.
            video_id: Video the failing call was about, if any.
            category: Triage category assigned by the retry layer, if known.
        """
        super().__init__(message)
        self.reason = reason
        self.status_code = status_code
        self.video_id = video_id
        self.category = category


class QuotaExhaustedError(APIError):
    """Raised when the YouTube API rejects a call because the daily quota is exhausted."""

    def __init__(
        self,
        message: str,
        *,
        reason: str = 'quotaexceeded',
        status_code: int | None = 403,
        video_id: str | None = None,
    ) -> None:
        """Initialize a quota error; the category is always ErrorCategory.QUOTA.

        Args:
            message: Human-readable description of the failure.
            reason: Normalized API error reason.
            status_code: HTTP status code returned by the API.
            video_id: Video the failing call was about, if any.
        """
        super().__init__(
            message, reason=reason, status_code=status_code, video_id=video_id, category=ErrorCategory.QUOTA
        )


class GitHubError(YouTubeTrackerError):
    """Raised when GitHub API operations fail (secrets update, repository access, etc.)."""
