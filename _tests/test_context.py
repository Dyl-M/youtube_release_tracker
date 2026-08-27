"""Tests for yrt/context.py - Per-job execution context and last-exe date parsing."""

# Standard library
import dataclasses
import datetime as dt
from pathlib import Path

# Third-party
import pytest
from tzlocal import get_localzone

# Local
from yrt import paths
from yrt.constants import EXE_MODE_ACTION, EXE_MODE_LOCAL, JOB_DAILY, JOB_UPDATES
from yrt.context import ExecutionContext, job_log_files, last_exe_date
from yrt.exceptions import ConfigurationError

NOW = dt.datetime(2024, 2, 1, 12, 30, tzinfo=dt.UTC)
LAST_EXE = dt.datetime(2024, 1, 31, 7, 0, tzinfo=dt.UTC)
FIRST_LINE = '2024-01-31 07:00:00+0000 [INFO] - Process started.\n'


def _context(**overrides):
    """Build a valid daily context on temp-looking paths, with optional field overrides."""
    fields = {
        'job': JOB_DAILY,
        'exe_mode': EXE_MODE_ACTION,
        'now': NOW,
        'last_exe': LAST_EXE,
        'history_path': Path('history.log'),
        'last_exe_path': Path('last_exe.log'),
    }
    fields.update(overrides)
    return ExecutionContext(**fields)


@pytest.mark.unit
class TestJobLogFiles:
    """Test job_log_files() resolves the per-job log pair from paths at call time."""

    @staticmethod
    def test_daily_job_uses_the_historical_files():
        """Test the daily job keeps history.log / last_exe.log."""
        assert job_log_files(JOB_DAILY) == (paths.HISTORY_LOG, paths.LAST_EXE_LOG)

    @staticmethod
    def test_updates_job_uses_its_own_files():
        """Test the frequent job gets the updates_* pair."""
        assert job_log_files(JOB_UPDATES) == (paths.UPDATES_HISTORY_LOG, paths.UPDATES_LAST_EXE_LOG)

    @staticmethod
    def test_paths_are_read_at_call_time(tmp_path, monkeypatch):
        """Test a monkeypatched paths module is honoured (the test-suite redirection pattern)."""
        monkeypatch.setattr(paths, 'HISTORY_LOG', tmp_path / 'h.log')
        monkeypatch.setattr(paths, 'LAST_EXE_LOG', tmp_path / 'l.log')

        assert job_log_files(JOB_DAILY) == (tmp_path / 'h.log', tmp_path / 'l.log')

    @staticmethod
    def test_unknown_job_is_rejected():
        """Test an unknown job name raises ValueError naming the valid jobs."""
        with pytest.raises(ValueError, match='Unknown job'):
            job_log_files('hourly')


@pytest.mark.unit
class TestLastExeDate:
    """Test last_exe_date() reads the previous run's start time from the first log line."""

    @staticmethod
    def test_parses_the_first_line(tmp_path):
        """Test the date of the first line is returned as an aware datetime."""
        log = tmp_path / 'last_exe.log'
        log.write_text(FIRST_LINE + '2024-01-31 07:00:05+0000 [INFO] - Process ended.\n', encoding='utf-8')

        assert last_exe_date(log) == LAST_EXE

    @staticmethod
    def test_missing_file_defaults_to_a_day_ago(tmp_path):
        """Test a first run (no file) yields 24 hours ago, timezone-aware."""
        before = dt.datetime.now(tz=get_localzone()) - dt.timedelta(days=1)

        result = last_exe_date(tmp_path / 'missing.log')

        assert result.utcoffset() is not None
        assert before <= result <= before + dt.timedelta(seconds=5)

    @staticmethod
    def test_empty_file_defaults_to_a_day_ago(tmp_path):
        """Test an empty file yields 24 hours ago."""
        log = tmp_path / 'last_exe.log'
        log.write_text('', encoding='utf-8')
        before = dt.datetime.now(tz=get_localzone()) - dt.timedelta(days=1)

        result = last_exe_date(log)

        assert before <= result <= before + dt.timedelta(seconds=5)

    @staticmethod
    def test_unparseable_first_line_raises(tmp_path):
        """Test a first line without a date raises ConfigurationError (caught and logged by run_job)."""
        log = tmp_path / 'last_exe.log'
        log.write_text('garbage\n', encoding='utf-8')

        with pytest.raises(ConfigurationError, match='Could not parse date') as exc_info:
            last_exe_date(log)

        assert exc_info.value.file_path == str(log)


@pytest.mark.unit
class TestExecutionContext:
    """Test ExecutionContext validation, properties and the create() factory."""

    @staticmethod
    def test_rejects_unknown_job():
        """Test the job name is validated."""
        with pytest.raises(ValueError, match='Unknown job'):
            _context(job='hourly')

    @staticmethod
    def test_rejects_unknown_exe_mode():
        """Test the execution mode is validated."""
        with pytest.raises(ValueError, match='Unknown execution mode'):
            _context(exe_mode='remote')

    @staticmethod
    @pytest.mark.parametrize('field', ['now', 'last_exe'])
    def test_rejects_naive_datetimes(field):
        """Test both datetimes must be timezone-aware."""
        with pytest.raises(ValueError, match='timezone-aware'):
            _context(**{field: dt.datetime(2024, 2, 1, 12, 30)})

    @staticmethod
    def test_is_frozen():
        """Test the context is declared frozen (fields are read-only; dataclasses.replace() derives a new one)."""
        assert ExecutionContext.__dataclass_params__.frozen is True
        assert dataclasses.replace(_context(), now=LAST_EXE).now == LAST_EXE

    @staticmethod
    def test_prog_bar_only_in_local_mode():
        """Test progress bars are enabled locally and disabled in the workflow."""
        assert _context(exe_mode=EXE_MODE_LOCAL).prog_bar is True
        assert _context(exe_mode=EXE_MODE_ACTION).prog_bar is False

    @staticmethod
    def test_create_reads_the_job_files(tmp_path, monkeypatch):
        """Test create() resolves the job's paths and reads last_exe from its last-exe log."""
        last_exe_log = tmp_path / 'updates_last_exe.log'
        last_exe_log.write_text(FIRST_LINE, encoding='utf-8')
        monkeypatch.setattr(paths, 'UPDATES_HISTORY_LOG', tmp_path / 'updates_history.log')
        monkeypatch.setattr(paths, 'UPDATES_LAST_EXE_LOG', last_exe_log)

        ctx = ExecutionContext.create(JOB_UPDATES, EXE_MODE_ACTION, now=NOW)

        assert ctx.job == JOB_UPDATES
        assert ctx.now == NOW
        assert ctx.last_exe == LAST_EXE
        assert ctx.history_path == tmp_path / 'updates_history.log'
        assert ctx.last_exe_path == last_exe_log

    @staticmethod
    def test_create_defaults_now_to_the_current_local_time(tmp_path, monkeypatch):
        """Test create() without now= stamps the current local time."""
        monkeypatch.setattr(paths, 'HISTORY_LOG', tmp_path / 'history.log')
        monkeypatch.setattr(paths, 'LAST_EXE_LOG', tmp_path / 'last_exe.log')
        before = dt.datetime.now(tz=get_localzone())

        ctx = ExecutionContext.create(JOB_DAILY, EXE_MODE_LOCAL)

        assert before <= ctx.now <= before + dt.timedelta(seconds=5)
        assert ctx.now.utcoffset() is not None
