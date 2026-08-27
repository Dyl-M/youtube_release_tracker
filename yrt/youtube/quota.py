"""Quota accounting for YouTube Data API calls.

The tracker only counts units in this phase: nothing refuses work when the budget is exceeded. It exists so the job
logs what it spent and so later phases can order work by value (adds, then removals, then sorting) and skip the
cheapest-to-lose steps first.
"""

# Local
from .. import config
from . import utils


class QuotaTracker:
    """Count YouTube Data API quota units spent by the current process."""

    def __init__(self, budget: int, *, daily_quota: int | None = None) -> None:
        """Create a tracker for one job run.

        Args:
            budget: Units this job is expected to stay under.
            daily_quota: Project-wide daily quota, for the summary line. Defaults to config.DAILY_QUOTA.

        Raises:
            ValueError: If budget is not a positive integer.
        """
        if budget < 1:
            raise ValueError(f'budget must be >= 1, got {budget}')

        self.budget = budget
        self.daily_quota = config.DAILY_QUOTA if daily_quota is None else daily_quota
        self._spent = 0
        self._calls = 0
        self._over_budget_logged = False

    @property
    def spent(self) -> int:
        """Units charged so far."""
        return self._spent

    @property
    def calls(self) -> int:
        """Number of charged API calls so far."""
        return self._calls

    @property
    def remaining(self) -> int:
        """Units left under the budget (never negative)."""
        return max(0, self.budget - self._spent)

    def charge(self, units: int) -> None:
        """Record one API call worth the given number of units.

        Args:
            units: Quota cost of the call (see constants.QUOTA_COST_*).

        Raises:
            ValueError: If units is negative.
        """
        if units < 0:
            raise ValueError(f'units must be >= 0, got {units}')

        self._spent += units
        self._calls += 1

        if self._spent > self.budget and not self._over_budget_logged:
            self._over_budget_logged = True
            if utils.history:
                utils.history.warning('Quota budget exceeded: %s units spent (budget %s).', self._spent, self.budget)

    def can_afford(self, units: int) -> bool:
        """Tell whether charging the given units would keep the job within its budget.

        Args:
            units: Quota cost of the call being considered.

        Returns:
            True if spent + units stays at or under the budget.
        """
        return self._spent + units <= self.budget

    def summary(self) -> str:
        """Build the one-line report logged at the end of a job.

        Returns:
            A line starting with 'Quota spent: N units'.
        """
        return (
            f'Quota spent: {self._spent} units ({self._calls} API call(s), '
            f'budget {self.budget}, daily quota {self.daily_quota}).'
        )

    def reset(self) -> None:
        """Forget everything charged so far."""
        self._spent = 0
        self._calls = 0
        self._over_budget_logged = False


class _DefaultTracker:
    """Holder for the process-wide tracker (a class attribute, so no module-level global statements are needed)."""

    instance: QuotaTracker | None = None


def get_tracker() -> QuotaTracker:
    """Return the process-wide tracker, creating it from config on first use.

    Returns:
        The default QuotaTracker.
    """
    tracker = _DefaultTracker.instance
    if tracker is None:
        tracker = QuotaTracker(config.DAILY_JOB_BUDGET, daily_quota=config.DAILY_QUOTA)
        _DefaultTracker.instance = tracker
    return tracker


def set_tracker(tracker: QuotaTracker) -> None:
    """Replace the process-wide tracker (used by jobs with their own budget, and by tests).

    Args:
        tracker: Tracker instance to use from now on.
    """
    _DefaultTracker.instance = tracker


def reset_tracker() -> None:
    """Drop the process-wide tracker so the next get_tracker() call rebuilds it from config."""
    _DefaultTracker.instance = None
