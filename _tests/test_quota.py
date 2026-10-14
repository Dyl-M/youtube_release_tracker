"""Tests for yrt/youtube/quota.py - Quota accounting."""

# Third-party
import pytest

# Local
from yrt.youtube import quota
from yrt.youtube.quota import QuotaTracker


@pytest.mark.unit
class TestQuotaTracker:
    """Test the QuotaTracker arithmetic and reporting."""

    @staticmethod
    def test_new_tracker_has_spent_nothing():
        """Test a fresh tracker reports zero spend, zero calls and the full budget remaining."""
        tracker = QuotaTracker(budget=100, daily_quota=1000)

        assert tracker.spent == 0
        assert tracker.calls == 0
        assert tracker.remaining == 100

    @staticmethod
    def test_charge_accumulates_units_and_calls():
        """Test charge() adds units and counts one call per charge."""
        tracker = QuotaTracker(budget=100, daily_quota=1000)

        tracker.charge(1)
        tracker.charge(50)

        assert tracker.spent == 51
        assert tracker.calls == 2
        assert tracker.remaining == 49

    @staticmethod
    def test_remaining_never_goes_negative():
        """Test remaining is clamped at zero once the budget is exceeded."""
        tracker = QuotaTracker(budget=60, daily_quota=1000)

        tracker.charge(50)
        tracker.charge(50)

        assert tracker.spent == 100
        assert tracker.remaining == 0

    @staticmethod
    def test_can_afford_boundary():
        """Test can_afford() is inclusive at exactly the budget."""
        tracker = QuotaTracker(budget=100, daily_quota=1000)
        tracker.charge(50)

        assert tracker.can_afford(50) is True
        assert tracker.can_afford(51) is False

    @staticmethod
    def test_negative_units_are_rejected():
        """Test charge() refuses negative units."""
        tracker = QuotaTracker(budget=100, daily_quota=1000)

        with pytest.raises(ValueError, match='units must be >= 0'):
            tracker.charge(-1)

    @staticmethod
    def test_budget_must_be_positive():
        """Test the tracker refuses a zero or negative budget."""
        with pytest.raises(ValueError, match='budget must be >= 1'):
            QuotaTracker(budget=0, daily_quota=1000)

    @staticmethod
    def test_summary_starts_with_quota_spent():
        """Test summary() produces the line the acceptance criterion greps for."""
        tracker = QuotaTracker(budget=7000, daily_quota=10000)
        tracker.charge(1)
        tracker.charge(50)

        line = tracker.summary()

        assert line.startswith('Quota spent: 51 units')
        assert '2 API call(s)' in line
        assert 'budget 7000' in line
        assert 'daily quota 10000' in line

    @staticmethod
    def test_reset_clears_everything():
        """Test reset() returns the tracker to its initial state."""
        tracker = QuotaTracker(budget=100, daily_quota=1000)
        tracker.charge(50)

        tracker.reset()

        assert tracker.spent == 0
        assert tracker.calls == 0

    @staticmethod
    def test_daily_quota_defaults_to_config():
        """Test the daily quota falls back to config.DAILY_QUOTA when not given."""
        from yrt import config

        assert QuotaTracker(budget=10).daily_quota == config.DAILY_QUOTA

    @staticmethod
    def test_over_budget_warning_logged_once(history_mock):
        """Test crossing the budget logs a single warning, not one per subsequent call."""
        tracker = QuotaTracker(budget=60, daily_quota=1000)

        tracker.charge(50)
        assert history_mock.warning.call_count == 0

        tracker.charge(50)
        tracker.charge(50)

        assert history_mock.warning.call_count == 1
        assert 'Quota budget exceeded' in history_mock.warning.call_args.args[0]


@pytest.mark.unit
class TestDefaultTracker:
    """Test the process-wide tracker helpers."""

    @staticmethod
    def test_get_tracker_builds_from_config():
        """Test the default tracker is created lazily with the daily job budget and daily quota."""
        from yrt import config

        tracker = quota.get_tracker()

        assert tracker.budget == config.DAILY_JOB_BUDGET
        assert tracker.daily_quota == config.DAILY_QUOTA
        assert quota.get_tracker() is tracker

    @staticmethod
    def test_set_tracker_replaces_default(quota_tracker):
        """Test set_tracker() makes the given instance the one get_tracker() returns."""
        assert quota.get_tracker() is quota_tracker

    @staticmethod
    def test_reset_tracker_forgets_default(quota_tracker):
        """Test reset_tracker() drops the current instance so the next call rebuilds one."""
        quota.reset_tracker()

        assert quota.get_tracker() is not quota_tracker
