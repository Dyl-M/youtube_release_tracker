"""Execution context: the per-run, per-job state that used to be computed at import time.

Each job (daily, updates) has its own history log and last-exe marker so the frequent job never shrinks the daily
look-back window. The context is built once by the entry point and passed explicitly to the functions that need the
time window or the log files - there is no process-wide default on purpose.
"""

# Standard library
import datetime as dt
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Self

# Third-party
import tzlocal

# Local
from . import paths
from .constants import EXE_MODE_LOCAL, EXE_MODES, JOB_DAILY, JOB_UPDATES, JOBS, LOG_DATE_FORMAT

# First token of a log line: "2026-08-27 09:12:00+0200"
_LOG_DATE_PATTERN = re.compile(r'(\d{4}(-\d{2}){2})\s(\d{2}:?){3}.[\d:]+')


def job_log_files(job: str) -> tuple[Path, Path]:
    """Return the (history log, last-exe log) pair of a job, read from paths at call time.

    Args:
        job: Job name, one of JOBS.

    Returns:
        The history log path and the last-exe log path.

    Raises:
        ValueError: If the job is unknown.
    """
    if job == JOB_DAILY:
        return paths.HISTORY_LOG, paths.LAST_EXE_LOG
    if job == JOB_UPDATES:
        return paths.UPDATES_HISTORY_LOG, paths.UPDATES_LAST_EXE_LOG
    raise ValueError(f'Unknown job {job!r}, expected one of {JOBS}')


def last_exe_date(log_path: Path) -> dt.datetime:
    """Get the last execution datetime from a last-exe log file.

    Args:
        log_path: The last-exe log of the job (its first line is the 'Process started.' line of the previous run).

    Returns:
        Last execution date, or 24 hours ago if the log is missing or empty.

    Raises:
        ValueError: If the first line holds no parseable date.
    """
    try:
        with open(log_path, encoding='utf8') as log_file:
            first_log = log_file.readline()

    except FileNotFoundError:
        # First run: default to 24 hours ago (daily workflow)
        return dt.datetime.now(tz=tzlocal.get_localzone()) - dt.timedelta(days=1)

    if not first_log:
        # Empty file: same default
        return dt.datetime.now(tz=tzlocal.get_localzone()) - dt.timedelta(days=1)

    match = _LOG_DATE_PATTERN.search(first_log)
    if match is None:
        raise ValueError(f'Could not parse date from log line: {first_log}')

    return dt.datetime.strptime(match.group(), LOG_DATE_FORMAT)


@dataclass(frozen=True)
class ExecutionContext:
    """What a single run of a job knows about itself.

    Attributes:
        job: Job name, one of JOBS.
        exe_mode: Execution mode, one of EXE_MODES.
        now: Timezone-aware start time of the run (upper bound of the discovery window).
        last_exe: Timezone-aware start time of the previous successful run (lower bound of the discovery window).
        history_path: History log of the job.
        last_exe_path: Last-exe log of the job (rewritten at the end of a successful run).
    """

    job: str
    exe_mode: str
    now: dt.datetime
    last_exe: dt.datetime
    history_path: Path
    last_exe_path: Path

    def __post_init__(self) -> None:
        """Validate the job name, the execution mode and the timezone awareness of both datetimes."""
        checks = (
            (self.job in JOBS, f'Unknown job {self.job!r}, expected one of {JOBS}'),
            (self.exe_mode in EXE_MODES, f'Unknown execution mode {self.exe_mode!r}, expected one of {EXE_MODES}'),
            (self.now.utcoffset() is not None, 'now must be timezone-aware'),
            (self.last_exe.utcoffset() is not None, 'last_exe must be timezone-aware'),
        )
        for valid, message in checks:
            if not valid:
                raise ValueError(message)

    @property
    def prog_bar(self) -> bool:
        """Whether progress bars are displayed (local runs only)."""
        return self.exe_mode == EXE_MODE_LOCAL

    @classmethod
    def create(cls, job: str, exe_mode: str, *, now: dt.datetime | None = None) -> Self:
        """Build the context of a run from the job's log files.

        Args:
            job: Job name, one of JOBS.
            exe_mode: Execution mode, one of EXE_MODES.
            now: Start time override (defaults to the current local time).

        Returns:
            The execution context, with last_exe read from the job's last-exe log.
        """
        history_path, last_exe_path = job_log_files(job)
        return cls(
            job=job,
            exe_mode=exe_mode,
            now=now or dt.datetime.now(tz=tzlocal.get_localzone()),
            last_exe=last_exe_date(last_exe_path),
            history_path=history_path,
            last_exe_path=last_exe_path,
        )
