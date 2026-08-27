"""Shared retry, error triage and quota accounting for YouTube Data API calls.

Every API call in the package goes through call_api(): transient failures are retried with exponential backoff and
jitter, every attempt that reached YouTube is charged to the quota tracker (YouTube bills rejected requests too,
except quota rejections), and anything that cannot be retried is raised as an APIError carrying the normalized
reason, HTTP status and triage category so call sites can decide what to do without parsing responses themselves.
"""

# Standard library
import math
import random
import time
from collections.abc import Callable
from dataclasses import dataclass

# Third-party
import pyyoutube as pyt
import requests

# Local
from .. import config
from ..constants import PERMANENT_ERRORS, QUOTA_ERRORS, TRANSIENT_ERRORS
from ..exceptions import APIError, ErrorCategory, QuotaExhaustedError
from . import quota, utils

# Exceptions the retry loop understands; anything else propagates untouched.
# JSONDecodeError: the client parses every body as JSON, so a 5xx served with an HTML page surfaces this way.
RETRYABLE_EXCEPTIONS: tuple[type[BaseException], ...] = (
    pyt.error.PyYouTubeException,
    requests.ConnectionError,
    requests.Timeout,
    requests.exceptions.JSONDecodeError,
)

UNKNOWN_REASON = 'unknown'


@dataclass(frozen=True)
class ErrorInfo:
    """What the retry layer learned about a failed call."""

    category: ErrorCategory
    reason: str
    status_code: int | None
    message: str


def normalise_reason(reason: str) -> str:
    """Normalize an API error reason for comparison with the constants' error sets.

    The API returns mixed formats (camelCase, SCREAMING_SNAKE_CASE); the sets are lowercase without underscores.

    Args:
        reason: Raw reason string from the API response.

    Returns:
        Lowercase reason with underscores removed.
    """
    return reason.lower().replace('_', '')


def extract_reason(error: pyt.error.PyYouTubeException) -> str:
    """Pull the normalized error reason out of a PyYouTubeException, if it carries an API response.

    PyYouTubeException.response is either a requests.Response (API-level error, reason available) or the library's
    ErrorMessage dataclass (client-side or HTTP-level error, no reason); only the former is inspected.

    Args:
        error: The exception raised by the client.

    Returns:
        Normalized reason, or 'unknown' when it cannot be determined.
    """
    response = error.response
    if not isinstance(response, requests.Response):
        return UNKNOWN_REASON

    try:
        reason = response.json()['error']['errors'][0]['reason']
    except (AttributeError, KeyError, IndexError, TypeError, ValueError):
        return UNKNOWN_REASON

    return normalise_reason(str(reason)) if reason else UNKNOWN_REASON


def classify(error: BaseException) -> ErrorInfo:
    """Assign a triage category to an exception raised by an API call.

    Args:
        error: The exception to classify.

    Returns:
        ErrorInfo with the category, normalized reason, HTTP status (if any) and message.
    """
    if isinstance(error, requests.ConnectionError):
        return ErrorInfo(ErrorCategory.TRANSIENT, 'connectionerror', None, str(error))

    if isinstance(error, requests.Timeout):
        return ErrorInfo(ErrorCategory.TRANSIENT, 'timeout', None, str(error))

    if isinstance(error, requests.exceptions.JSONDecodeError):
        return ErrorInfo(ErrorCategory.TRANSIENT, 'invalidresponse', None, str(error))

    if isinstance(error, pyt.error.PyYouTubeException):
        reason = extract_reason(error)

        if reason in TRANSIENT_ERRORS:
            category = ErrorCategory.TRANSIENT
        elif reason in PERMANENT_ERRORS:
            category = ErrorCategory.PERMANENT
        elif reason in QUOTA_ERRORS:
            category = ErrorCategory.QUOTA
        else:
            category = ErrorCategory.UNKNOWN

        return ErrorInfo(category, reason, error.status_code, error.message or '')

    return ErrorInfo(ErrorCategory.UNKNOWN, UNKNOWN_REASON, None, str(error))


def backoff_delay(attempt: int) -> float:
    """Compute the wait before the next attempt: exponential backoff, capped, with equal jitter.

    Args:
        attempt: Zero-based index of the attempt that just failed.

    Returns:
        Seconds to sleep, within [delay / 2, delay] where delay = min(MAX_BACKOFF, BASE_DELAY * e**attempt).
    """
    delay = min(config.MAX_BACKOFF, int(config.BASE_DELAY * math.exp(attempt)))
    return delay / 2 + random.uniform(0, delay / 2)  # noqa: S311 - jitter, not cryptography


def _reached_youtube(error: BaseException) -> bool:
    """Tell whether a failed attempt was actually received by YouTube (and therefore billed).

    A connection error (DNS, refused, reset before a response) never reached the API; everything else - including a
    read timeout, which is ambiguous - is charged, matching YouTube's "every request costs" rule.

    Args:
        error: The exception the attempt raised.

    Returns:
        False for connection-level failures, True otherwise.
    """
    return not isinstance(error, requests.ConnectionError)


def _to_api_error(info: ErrorInfo, description: str, video_id: str | None) -> APIError:
    """Turn a classified failure into the exception raised to the call site.

    Args:
        info: Classification of the failure.
        description: Human-readable name of the call (for the message).
        video_id: Video the call was about, if any.

    Returns:
        QuotaExhaustedError for quota failures, APIError otherwise.
    """
    message = f'{description}: {info.message} (reason={info.reason}, status={info.status_code})'

    if info.category is ErrorCategory.QUOTA:
        return QuotaExhaustedError(message, reason=info.reason, status_code=info.status_code, video_id=video_id)

    return APIError(
        message, reason=info.reason, status_code=info.status_code, video_id=video_id, category=info.category
    )


def rewrap(error: APIError, description: str, *, video_id: str | None = None, log: bool = True) -> APIError:
    """Add a call-site prefix to an APIError raised further down, keeping its type and context.

    Use as ``raise retry.rewrap(error, 'API error while getting stats') from error``.

    Args:
        error: The error raised by call_api() or a function built on it.
        description: Prefix naming the operation that failed.
        video_id: Video the operation was about; defaults to the one already on the error.
        log: Whether to log the failure on the shared logger before returning.

    Returns:
        A QuotaExhaustedError if the original was one, otherwise an APIError with the same reason, status and
        category.
    """
    message = f'{description}: {error}'
    video = video_id if video_id is not None else error.video_id

    if log and utils.history:
        utils.history.error(message)

    if isinstance(error, QuotaExhaustedError):
        return QuotaExhaustedError(
            message, reason=error.reason or 'quotaexceeded', status_code=error.status_code, video_id=video
        )

    return APIError(
        message, reason=error.reason, status_code=error.status_code, video_id=video, category=error.category
    )


def call_api[T](fn: Callable[[], T], *, cost: int, description: str, video_id: str | None = None) -> T:
    """Run one YouTube API call with retry, triage and quota accounting.

    config.MAX_RETRIES is the total number of attempts (a value of 0 still makes one attempt).

    Args:
        fn: Zero-argument callable performing the call (typically a functools.partial on the client).
        cost: Quota units of the call (constants.QUOTA_COST_LIST or QUOTA_COST_WRITE).
        description: Short name for logs and error messages, e.g. 'playlistItems.insert'.
        video_id: Video the call is about, carried on the raised APIError.

    Returns:
        Whatever fn returns.

    Raises:
        QuotaExhaustedError: If the API rejected the call for quota reasons.
        APIError: For permanent or unknown failures, or when transient retries are exhausted.
    """
    tracker = quota.get_tracker()
    attempts = max(1, config.MAX_RETRIES)

    for attempt in range(attempts):
        try:
            result = fn()

        except RETRYABLE_EXCEPTIONS as error:
            info = classify(error)

            # Quota rejections and connection-level failures never consumed units
            if info.category is not ErrorCategory.QUOTA and _reached_youtube(error):
                tracker.charge(cost)

            if info.category is ErrorCategory.TRANSIENT and attempt < attempts - 1:
                wait_time = backoff_delay(attempt)
                if utils.history:
                    utils.history.warning(
                        'Transient error (%s) on %s, retrying in %.2fs (attempt %s/%s)',
                        info.reason,
                        description,
                        wait_time,
                        attempt + 1,
                        attempts,
                    )
                time.sleep(wait_time)
                continue

            raise _to_api_error(info, description, video_id) from error

        tracker.charge(cost)
        return result

    raise AssertionError('unreachable: the retry loop always returns or raises')
