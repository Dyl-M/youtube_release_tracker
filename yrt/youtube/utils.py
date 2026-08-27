"""Utility functions and the shared logger for YouTube operations."""

# Standard library
import datetime as dt
import itertools
from collections.abc import Sequence
from typing import Any

# Third-party
import isodate
import requests

# Local
from .. import config
from ..constants import (
    ISO_DATE_FORMAT,
    PERMANENT_ERRORS,
    QUOTA_ERRORS,
    TRANSIENT_ERRORS,
)

# Re-export for backward compatibility
__all__ = [
    # Functions
    'parse_iso8601_duration',
    'is_shorts',
    'chunked',
    # Constants (re-exported from yrt.constants)
    'TRANSIENT_ERRORS',
    'PERMANENT_ERRORS',
    'QUOTA_ERRORS',
    'ISO_DATE_FORMAT',
]


def chunked[T](sequence: Sequence[T], size: int) -> list[list[T]]:
    """Split a sequence into consecutive chunks of at most size items.

    Args:
        sequence: The sequence to split.
        size: Maximum number of items per chunk (must be >= 1).

    Returns:
        A list of chunks, each a list with at most size items.
    """
    return [list(batch) for batch in itertools.batched(sequence, size)]


def parse_iso8601_duration(duration_str: str | None) -> int:
    """Convert an ISO 8601 duration (e.g. 'PT1H30M') to whole seconds.

    Unlike timedelta.seconds, the result keeps the days component, so a 30-hour stream is 108000 and not 21600.

    Args:
        duration_str: Duration as returned by the API in contentDetails.duration; None or empty means unknown.

    Returns:
        Duration in seconds; 0 when unknown or unparseable (logged as a warning).
    """
    if not duration_str:
        return 0

    try:
        parsed = isodate.parse_duration(duration_str)
    except (TypeError, ValueError):  # isodate.ISO8601Error is a ValueError
        if history:
            history.warning('Could not parse video duration %r, defaulting to 0 seconds.', duration_str)
        return 0

    if not isinstance(parsed, dt.timedelta):  # isodate.Duration (years/months) is never emitted by YouTube
        if history:
            history.warning('Unsupported duration %r (years/months), defaulting to 0 seconds.', duration_str)
        return 0

    return int(parsed.total_seconds())


# Logger placeholder - set by __init__.py at import and rebound by runtime.bootstrap() to the job's history file
history: Any = None


def set_logger(logger: Any) -> None:
    """Set the shared logger instance.

    Args:
        logger: Logger instance to use for this module.
    """
    global history  # skipcq: PYL-W0603 - intentional module-level state for dependency injection
    history = logger


def is_shorts(video_id: str) -> bool:
    """Check if a YouTube video is a short or not.

    Args:
        video_id: YouTube video ID.

    Returns:
        True if the video is short, False otherwise. Returns False on network errors.
    """
    try:
        response = requests.head(
            f'https://www.youtube.com/shorts/{video_id}', timeout=config.NETWORK_TIMEOUT, allow_redirects=False
        )
        return response.status_code == 200

    except Exception as error:
        if history:
            history.warning('Failed to check shorts status for video %s: %s', video_id, str(error))
        return False  # Default to non-short on error
