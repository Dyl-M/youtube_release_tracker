"""Tests for yrt/updates.py - The frequent job: CLI entry point, run_updates orchestration and a full local run.

Detection and the playlist update themselves are covered by test_lives.py.
"""

# Standard library
import datetime as dt
from unittest.mock import DEFAULT, MagicMock, patch

# Third-party
import pytest

# Local
from yrt import config, paths, runtime, updates
from yrt.constants import (
    EXE_MODE_ACTION,
    EXE_MODE_LOCAL,
    JOB_UPDATES,
    LIVE_STATUS_LIVE,
    PROCESS_END_MARKER,
    PROCESS_START_MARKER,
)
from yrt.exceptions import APIError, QuotaExhaustedError
from yrt.models import AddOnConfig, AppConfig, LiveStream, PlaylistConfig

MUSIC_CHANNEL = 'UCmusic0000000000000000'
CERTIFIED_CHANNEL = 'UCcertified000000000000'
SKIPPED_CHANNEL = 'UCskipped00000000000000'


def _app_config():
    """Build an AppConfig with music, certified (one shared) and skipped channels, and every required playlist."""
    playlists = {
        key: PlaylistConfig(id=f'PL{key:_<32}'[:34], name=key, description='') for key in runtime.REQUIRED_PLAYLISTS
    }
    pocket_tube = {'MUSIQUE': [MUSIC_CHANNEL, SKIPPED_CHANNEL], 'APPRENTISSAGE': [], 'DIVERTISSEMENT': [], 'GAMING': []}
    add_on = AddOnConfig(favorites={}, certified=[CERTIFIED_CHANNEL, MUSIC_CHANNEL], to_pass=[SKIPPED_CHANNEL])
    return AppConfig(pocket_tube=pocket_tube, playlists=playlists, add_on=add_on)


@pytest.fixture
def updates_config(monkeypatch):
    """Serve a minimal AppConfig through runtime.load_config(); returns it."""
    cfg = _app_config()
    monkeypatch.setattr(runtime, 'load_config', lambda: cfg)
    return cfg


@pytest.fixture
def lives_mocks():
    """Patch the youtube functions run_updates() calls; detection finds one live."""
    live = LiveStream(video_id='live1', channel_id=MUSIC_CHANNEL, title='t', status=LIVE_STATUS_LIVE)
    with patch.multiple('yrt.updates.youtube', find_live_streams=DEFAULT, update_lives_playlist=DEFAULT) as mocks:
        mocks['find_live_streams'].return_value = [live]
        mocks['update_lives_playlist'].return_value = (['live1'], [])
        yield mocks


@pytest.fixture
def updates_context(exec_context):
    """The shared execution context, as the frequent job."""
    return runtime.ExecutionContext(**{**vars(exec_context), 'job': JOB_UPDATES})


@pytest.mark.unit
class TestUpdatesEntryPoint:
    """Test main() hands the frequent job to the runtime."""

    @staticmethod
    def test_runs_the_updates_job_in_the_requested_mode():
        """Test 'action' hands the updates job and the workflow mode to run_job() and returns its exit code."""
        with patch('yrt.updates.runtime.run_job', return_value=0) as run_job:
            assert updates.main(['action']) == 0

        assert run_job.call_args.args == (JOB_UPDATES, EXE_MODE_ACTION, updates.run_updates)

    @staticmethod
    def test_defaults_to_local_mode():
        """Test no argument means local mode."""
        with patch('yrt.updates.runtime.run_job', return_value=0) as run_job:
            updates.main([])

        assert run_job.call_args.args == (JOB_UPDATES, EXE_MODE_LOCAL, updates.run_updates)


@pytest.mark.integration
class TestRunUpdates:
    """Test run_updates() orchestration against patched youtube functions."""

    @staticmethod
    def test_detects_on_music_and_certified_then_updates_music_lives(
        updates_context, session_factory, updates_config, lives_mocks
    ):
        """Test MUSIQUE then certified (de-duplicated) are scanned with the grace period, result to music_lives."""
        session = session_factory()

        updates.run_updates(updates_context, session)

        detect = lives_mocks['find_live_streams'].call_args
        assert detect.args[1] == [MUSIC_CHANNEL, SKIPPED_CHANNEL, CERTIFIED_CHANNEL]
        stale_before = updates_context.now - dt.timedelta(hours=config.LIVES_UPCOMING_GRACE_HOURS)
        assert detect.kwargs == {'stale_before': stale_before, 'to_pass': [SKIPPED_CHANNEL], 'prog_bar': False}

        update = lives_mocks['update_lives_playlist'].call_args
        assert update.args[1] == updates_config.playlists['music_lives'].id
        assert [stream.video_id for stream in update.args[2]] == ['live1']
        assert update.kwargs == {
            'stale_before': stale_before,
            'max_per_channel': config.LIVES_MAX_PER_CHANNEL,
            'prog_bar': False,
        }

    @staticmethod
    def test_quota_exhaustion_is_not_fatal(updates_context, session_factory, updates_config, lives_mocks, log_lines):
        """Test a quota rejection is logged as a warning and the job body returns normally."""
        lives_mocks['update_lives_playlist'].side_effect = QuotaExhaustedError('quota wall')

        updates.run_updates(updates_context, session_factory())

        assert 'Quota exhausted, lives update stopped: quota wall' in log_lines(updates_context.history_path)

    @staticmethod
    def test_other_api_errors_propagate(updates_context, session_factory, updates_config, lives_mocks):
        """Test any other API failure reaches run_job() (fatal error, exit code 1)."""
        lives_mocks['find_live_streams'].side_effect = APIError('broken')

        with pytest.raises(APIError):
            updates.run_updates(updates_context, session_factory())


@pytest.mark.integration
class TestUpdatesLogs:
    """Test a full local run writes the frequent job's own log files and leaves the daily ones alone."""

    @staticmethod
    def test_success_uses_the_updates_log_files(tmp_path, monkeypatch, updates_config, lives_mocks, log_lines):
        """Test history and last-exe go to the updates files, with the job's quota budget in the summary."""
        for name in ('HISTORY_LOG', 'LAST_EXE_LOG', 'UPDATES_HISTORY_LOG', 'UPDATES_LAST_EXE_LOG'):
            monkeypatch.setattr(paths, name, tmp_path / f'{name.lower()}.log')

        with (
            patch('yrt.runtime.youtube.create_service_local', return_value=MagicMock()),
            patch('yrt.runtime.youtube.encode_key'),
        ):
            assert updates.main([]) == 0

        lines = log_lines(tmp_path / 'updates_last_exe_log.log')
        assert lines[0] == PROCESS_START_MARKER
        assert lines[-1] == PROCESS_END_MARKER
        assert f'budget {config.UPDATES_JOB_BUDGET}' in lines[-2]
        assert not (tmp_path / 'history_log.log').exists()
        assert not (tmp_path / 'last_exe_log.log').exists()
