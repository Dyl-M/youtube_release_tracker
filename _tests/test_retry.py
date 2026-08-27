"""Tests for yrt/youtube/retry.py - Retry, error triage and quota charging."""

# Standard library
from unittest.mock import Mock, patch

# Third-party
import pytest
import requests
from pyyoutube.error import ErrorMessage, PyYouTubeException

# Local
from yrt import config
from yrt.constants import QUOTA_COST_LIST, QUOTA_COST_WRITE
from yrt.exceptions import APIError, ErrorCategory, QuotaExhaustedError
from yrt.youtube.retry import (
    UNKNOWN_REASON,
    backoff_delay,
    call_api,
    classify,
    extract_reason,
    normalise_reason,
    rewrap,
)


@pytest.mark.unit
class TestNormaliseReason:
    """Test reason normalization against the constants' error sets."""

    @staticmethod
    def test_screaming_snake_case():
        """Test SCREAMING_SNAKE_CASE reasons become lowercase without underscores."""
        assert normalise_reason('SERVICE_UNAVAILABLE') == 'serviceunavailable'

    @staticmethod
    def test_camel_case():
        """Test camelCase reasons become lowercase."""
        assert normalise_reason('quotaExceeded') == 'quotaexceeded'


@pytest.mark.unit
class TestExtractReason:
    """Test reason extraction from the two shapes a PyYouTubeException can carry."""

    @staticmethod
    def test_response_backed_error_yields_reason(api_error):
        """Test an API-level error exposes its normalized reason."""
        assert extract_reason(api_error('error_quota_exceeded.json')) == 'quotaexceeded'

    @staticmethod
    def test_error_message_backed_error_is_unknown():
        """Test a client-side error (ErrorMessage, no HTTP body) yields 'unknown' instead of crashing."""
        error = PyYouTubeException(ErrorMessage(status_code=10000, message='HTTP error'))

        assert extract_reason(error) == UNKNOWN_REASON

    @staticmethod
    def test_body_without_errors_list_is_unknown():
        """Test an API body missing the errors list yields 'unknown'."""
        response = Mock(spec=requests.Response)
        response.status_code = 500
        response.json.return_value = {'error': {'code': 500, 'message': 'boom'}}

        assert extract_reason(PyYouTubeException(response)) == UNKNOWN_REASON

    @staticmethod
    def test_unparseable_body_is_unknown():
        """Test a body that fails to decode as JSON on re-read yields 'unknown'."""
        response = Mock(spec=requests.Response)
        response.status_code = 500
        response.json.side_effect = [{'error': {'code': 500, 'message': 'boom'}}, ValueError('not json')]

        assert extract_reason(PyYouTubeException(response)) == UNKNOWN_REASON


@pytest.mark.unit
class TestClassify:
    """Test the triage category assigned to each kind of failure."""

    @staticmethod
    def test_quota_exceeded(api_error):
        """Test quotaExceeded is QUOTA with the HTTP status carried over."""
        info = classify(api_error('error_quota_exceeded.json'))

        assert info.category is ErrorCategory.QUOTA
        assert info.reason == 'quotaexceeded'
        assert info.status_code == 403

    @staticmethod
    def test_forbidden_is_permanent(api_error):
        """Test forbidden is PERMANENT."""
        info = classify(api_error('error_403_response.json'))

        assert info.category is ErrorCategory.PERMANENT
        assert info.reason == 'forbidden'

    @staticmethod
    def test_backend_error_is_transient(api_error):
        """Test backendError is TRANSIENT with status 503."""
        info = classify(api_error('error_503_backend.json'))

        assert info.category is ErrorCategory.TRANSIENT
        assert info.status_code == 503

    @staticmethod
    def test_playlist_not_found_is_unknown_with_404(api_error):
        """Test playlistNotFound is not in any set, so it is UNKNOWN but keeps its 404 for call sites."""
        info = classify(api_error('error_404_response.json'))

        assert info.category is ErrorCategory.UNKNOWN
        assert info.reason == 'playlistnotfound'
        assert info.status_code == 404

    @staticmethod
    def test_connection_error_is_transient():
        """Test a requests ConnectionError is TRANSIENT without a status."""
        info = classify(requests.ConnectionError('reset by peer'))

        assert info.category is ErrorCategory.TRANSIENT
        assert info.reason == 'connectionerror'
        assert info.status_code is None

    @staticmethod
    def test_timeout_is_transient():
        """Test a requests Timeout is TRANSIENT."""
        info = classify(requests.Timeout('read timed out'))

        assert info.category is ErrorCategory.TRANSIENT
        assert info.reason == 'timeout'

    @staticmethod
    def test_invalid_json_body_is_transient():
        """Test a JSONDecodeError (non-JSON 5xx page) is TRANSIENT."""
        info = classify(requests.exceptions.JSONDecodeError('Expecting value', '<html>', 0))

        assert info.category is ErrorCategory.TRANSIENT
        assert info.reason == 'invalidresponse'

    @staticmethod
    def test_unrelated_exception_is_unknown():
        """Test anything the layer does not understand is UNKNOWN."""
        info = classify(RuntimeError('what'))

        assert info.category is ErrorCategory.UNKNOWN
        assert info.reason == UNKNOWN_REASON


@pytest.mark.unit
class TestBackoffDelay:
    """Test the exponential backoff with equal jitter."""

    @staticmethod
    def test_delay_within_jitter_window():
        """Test the delay lies within [delay / 2, delay] for the first attempt."""
        base = config.BASE_DELAY

        for _ in range(20):
            assert base / 2 <= backoff_delay(0) <= base

    @staticmethod
    def test_delay_is_capped_by_max_backoff():
        """Test very late attempts never exceed MAX_BACKOFF."""
        with patch('yrt.youtube.retry.random.uniform', side_effect=lambda _low, high: high):
            assert backoff_delay(50) == config.MAX_BACKOFF

    @staticmethod
    def test_delay_grows_with_attempts():
        """Test the upper bound of the delay grows between attempt 0 and attempt 3."""
        with patch('yrt.youtube.retry.random.uniform', side_effect=lambda _low, high: high):
            assert backoff_delay(3) > backoff_delay(0)


@pytest.mark.unit
class TestCallApi:
    """Test call_api() retry semantics and quota charging."""

    @staticmethod
    def test_success_returns_result_and_charges_once(quota_tracker):
        """Test a successful call returns fn's result and charges exactly its cost."""
        fn = Mock(return_value='ok')

        assert call_api(fn, cost=QUOTA_COST_LIST, description='videos.list') == 'ok'
        assert fn.call_count == 1
        assert quota_tracker.spent == QUOTA_COST_LIST
        assert quota_tracker.calls == 1

    @staticmethod
    def test_transient_errors_are_retried_then_succeed(api_error, quota_tracker, no_sleep):
        """Test two transient failures then success: three attempts, three charges, two sleeps."""
        fn = Mock(side_effect=[api_error('error_503_backend.json'), api_error('error_503_backend.json'), 'ok'])

        assert call_api(fn, cost=QUOTA_COST_WRITE, description='playlistItems.insert') == 'ok'
        assert fn.call_count == 3
        assert quota_tracker.spent == 3 * QUOTA_COST_WRITE
        assert no_sleep.call_count == 2

    @staticmethod
    def test_transient_errors_exhaust_retries(api_error, quota_tracker, no_sleep):
        """Test MAX_RETRIES transient failures raise an APIError with the TRANSIENT category."""
        fn = Mock(side_effect=api_error('error_503_backend.json'))

        with pytest.raises(APIError) as exc_info:
            call_api(fn, cost=QUOTA_COST_LIST, description='videos.list')

        assert exc_info.value.category is ErrorCategory.TRANSIENT
        assert exc_info.value.status_code == 503
        assert fn.call_count == config.MAX_RETRIES
        assert no_sleep.call_count == config.MAX_RETRIES - 1
        assert quota_tracker.spent == config.MAX_RETRIES * QUOTA_COST_LIST

    @staticmethod
    def test_permanent_error_is_not_retried(api_error, quota_tracker, no_sleep):
        """Test a permanent error raises immediately with reason, status and video ID attached."""
        fn = Mock(side_effect=api_error('error_403_response.json'))

        with pytest.raises(APIError) as exc_info:
            call_api(fn, cost=QUOTA_COST_WRITE, description='playlistItems.insert', video_id='dQw4w9WgXcQ')

        error = exc_info.value
        assert error.category is ErrorCategory.PERMANENT
        assert error.reason == 'forbidden'
        assert error.status_code == 403
        assert error.video_id == 'dQw4w9WgXcQ'
        assert 'playlistItems.insert' in str(error)
        assert fn.call_count == 1
        assert no_sleep.call_count == 0
        assert quota_tracker.spent == QUOTA_COST_WRITE

    @staticmethod
    def test_quota_error_raises_quota_exhausted_without_charging(api_error, quota_tracker, no_sleep):
        """Test a quota rejection raises QuotaExhaustedError and is the one failure not charged."""
        fn = Mock(side_effect=api_error('error_quota_exceeded.json'))

        with pytest.raises(QuotaExhaustedError) as exc_info:
            call_api(fn, cost=QUOTA_COST_WRITE, description='playlistItems.insert', video_id='dQw4w9WgXcQ')

        assert exc_info.value.category is ErrorCategory.QUOTA
        assert exc_info.value.video_id == 'dQw4w9WgXcQ'
        assert fn.call_count == 1
        assert quota_tracker.spent == 0
        assert quota_tracker.calls == 0

    @staticmethod
    def test_unknown_error_raises_with_status(api_error, quota_tracker, no_sleep):
        """Test an unrecognized reason raises an UNKNOWN APIError that still carries its HTTP status."""
        fn = Mock(side_effect=api_error('error_404_response.json'))

        with pytest.raises(APIError) as exc_info:
            call_api(fn, cost=QUOTA_COST_LIST, description='playlistItems.list')

        assert exc_info.value.category is ErrorCategory.UNKNOWN
        assert exc_info.value.status_code == 404
        assert fn.call_count == 1

    @staticmethod
    def test_error_message_backed_exception_does_not_crash(quota_tracker, no_sleep):
        """Test a client-side PyYouTubeException (no HTTP body) is handled as UNKNOWN, not AttributeError."""
        fn = Mock(side_effect=PyYouTubeException(ErrorMessage(status_code=10000, message='HTTP error')))

        with pytest.raises(APIError) as exc_info:
            call_api(fn, cost=QUOTA_COST_LIST, description='videos.list')

        assert exc_info.value.category is ErrorCategory.UNKNOWN
        assert exc_info.value.reason == UNKNOWN_REASON

    @staticmethod
    def test_connection_error_is_retried_but_not_charged(quota_tracker, no_sleep):
        """Test a requests ConnectionError is retried, and only the attempt that reached YouTube is charged."""
        fn = Mock(side_effect=[requests.ConnectionError('reset'), 'ok'])

        assert call_api(fn, cost=QUOTA_COST_LIST, description='videos.list') == 'ok'
        assert fn.call_count == 2
        assert no_sleep.call_count == 1
        assert quota_tracker.spent == QUOTA_COST_LIST

    @staticmethod
    def test_invalid_json_response_is_retried_and_charged(quota_tracker, no_sleep):
        """Test a 5xx served as HTML (JSONDecodeError inside the client) is transient and billed."""
        fn = Mock(side_effect=[requests.exceptions.JSONDecodeError('Expecting value', '<html>', 0), 'ok'])

        assert call_api(fn, cost=QUOTA_COST_LIST, description='videos.list') == 'ok'
        assert fn.call_count == 2
        assert quota_tracker.spent == 2 * QUOTA_COST_LIST

    @staticmethod
    def test_read_timeout_is_charged(quota_tracker, no_sleep):
        """Test a read timeout (the request may have reached YouTube) is charged like any other attempt."""
        fn = Mock(side_effect=[requests.ReadTimeout('read timed out'), 'ok'])

        call_api(fn, cost=QUOTA_COST_LIST, description='videos.list')

        assert quota_tracker.spent == 2 * QUOTA_COST_LIST

    @staticmethod
    def test_zero_max_retries_means_one_attempt(api_error, quota_tracker, no_sleep, monkeypatch):
        """Test MAX_RETRIES = 0 still performs exactly one attempt instead of skipping the call."""
        monkeypatch.setattr(config, 'MAX_RETRIES', 0)
        fn = Mock(side_effect=api_error('error_503_backend.json'))

        with pytest.raises(APIError):
            call_api(fn, cost=QUOTA_COST_LIST, description='videos.list')

        assert fn.call_count == 1
        assert no_sleep.call_count == 0

    @staticmethod
    def test_retry_is_logged(api_error, quota_tracker, no_sleep, history_mock):
        """Test each retry writes one warning naming the reason and the call."""
        fn = Mock(side_effect=[api_error('error_503_backend.json'), 'ok'])

        call_api(fn, cost=QUOTA_COST_LIST, description='videos.list')

        assert history_mock.warning.call_count == 1
        args = history_mock.warning.call_args.args
        assert 'Transient error' in args[0]
        assert args[1] == 'backenderror'
        assert args[2] == 'videos.list'

    @staticmethod
    def test_unrelated_exceptions_propagate_untouched(quota_tracker):
        """Test exceptions outside RETRYABLE_EXCEPTIONS are neither retried nor wrapped."""
        fn = Mock(side_effect=RuntimeError('bug in caller'))

        with pytest.raises(RuntimeError, match='bug in caller'):
            call_api(fn, cost=QUOTA_COST_LIST, description='videos.list')

        assert quota_tracker.spent == 0


@pytest.mark.unit
class TestRewrap:
    """Test rewrap() adds a prefix while keeping the error's type and context."""

    @staticmethod
    def test_keeps_api_error_context(history_mock):
        """Test an APIError is re-created with the prefix and the same reason / status / category."""
        original = APIError('videos.list: boom', reason='forbidden', status_code=403, category=ErrorCategory.PERMANENT)

        wrapped = rewrap(original, 'API error while getting stats')

        assert str(wrapped) == 'API error while getting stats: videos.list: boom'
        assert wrapped.reason == 'forbidden'
        assert wrapped.status_code == 403
        assert wrapped.category is ErrorCategory.PERMANENT
        assert history_mock.error.call_count == 1

    @staticmethod
    def test_keeps_quota_exhausted_type_and_video_id(history_mock):
        """Test a QuotaExhaustedError stays a QuotaExhaustedError and keeps its video ID."""
        original = QuotaExhaustedError('insert: quota', video_id='dQw4w9WgXcQ')

        wrapped = rewrap(original, 'API error while adding')

        assert isinstance(wrapped, QuotaExhaustedError)
        assert wrapped.category is ErrorCategory.QUOTA
        assert wrapped.video_id == 'dQw4w9WgXcQ'

    @staticmethod
    def test_log_can_be_disabled(history_mock):
        """Test log=False keeps the shared logger quiet (maintenance scripts)."""
        rewrap(APIError('x'), 'prefix', log=False)

        assert history_mock.error.call_count == 0
