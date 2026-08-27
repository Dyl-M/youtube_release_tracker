"""Tests for yrt/main.py - The daily job: side-effect-free import, CLI entry point and run_daily orchestration.

Video routing itself is covered by test_router.py; the lifecycle (bootstrap, finalize, run_job) by test_runtime.py.
"""

# Standard library
import datetime as dt
from unittest.mock import DEFAULT, MagicMock, patch

# Third-party
import pandas as pd
import pytest

# Local
from yrt import main, paths, router, runtime
from yrt.constants import EXE_MODE_ACTION, EXE_MODE_LOCAL, JOB_DAILY, PROCESS_END_MARKER, PROCESS_START_MARKER
from yrt.exceptions import APIError, CredentialsError
from yrt.models import AddOnConfig, AppConfig, PlaylistConfig, PlaylistItem

MUSIC_CHANNEL = 'UCmusic0000000000000000'
YOUTUBE_FUNCTIONS = (
    'add_api_fail',
    'iter_channels',
    'weekly_stats',
    'add_stats',
    'add_to_playlist',
    'fill_release_radar',
    'cleanup_expired_videos',
    'cleanup_ended_streams',
)


def _app_config():
    """Build an AppConfig with one music channel and every required playlist."""
    playlists = {
        key: PlaylistConfig(id=f'PL{key:_<32}'[:34], name=key, description='') for key in runtime.REQUIRED_PLAYLISTS
    }
    pocket_tube = {'MUSIQUE': [MUSIC_CHANNEL], 'APPRENTISSAGE': [], 'DIVERTISSEMENT': [], 'GAMING': []}
    return AppConfig(pocket_tube=pocket_tube, playlists=playlists, add_on=AddOnConfig(favorites={}))


def _new_video_frame(video_id):
    """Build the DataFrame add_stats() returns for one regular music video."""
    return pd.DataFrame(
        [
            {
                'video_id': video_id,
                'video_title': 'Title',
                'item_id': f'item_{video_id}',
                'release_date': dt.datetime(2024, 1, 15, 12, tzinfo=dt.UTC),
                'status': 'public',
                'channel_id': MUSIC_CHANNEL,
                'channel_name': 'Music',
                'source_channel_id': MUSIC_CHANNEL,
                'views': 10,
                'likes': 1,
                'comments': 0,
                'duration': 200,
                'is_shorts': False,
                'live_status': 'none',
                'latest_status': 'public',
            }
        ]
    )


@pytest.fixture
def daily_config(tmp_path, monkeypatch):
    """Serve a minimal AppConfig, an empty temp stats.csv and a fresh router singleton; returns the config."""
    cfg = _app_config()
    stats = tmp_path / 'stats.csv'
    pd.DataFrame(columns=list(main.STATS_COLUMNS)).to_csv(stats, index=False)
    monkeypatch.setattr(paths, 'STATS_CSV', stats)
    monkeypatch.setattr(runtime, 'load_config', lambda: cfg)
    monkeypatch.setattr(router, '_default_router', None)
    return cfg


@pytest.fixture
def session(session_factory):
    """A Session with a mock service and a logger on the context's history file."""
    return session_factory()


@pytest.fixture
def youtube_mocks():
    """Patch every youtube function run_daily() calls; weekly_stats returns its input unchanged."""
    with patch.multiple('yrt.main.youtube', **dict.fromkeys(YOUTUBE_FUNCTIONS, DEFAULT)) as mocks:
        mocks['weekly_stats'].side_effect = lambda service, histo_data, week_delta, ref_date: histo_data
        mocks['iter_channels'].return_value = []
        yield mocks


@pytest.mark.unit
class TestModuleImport:
    """Test importing yrt.main does no work."""

    @staticmethod
    def test_import_has_no_side_effects():
        """Test the old import-time globals (argv mode, config, router, stats) no longer exist."""
        for name in ('exe_mode', 'histo_data', 'pocket_tube', 'playlists', 'video_router', 'github_repo'):
            assert not hasattr(main, name)

    @staticmethod
    def test_main_is_callable():
        """Test the entry point exists."""
        assert callable(main.main)


@pytest.mark.unit
class TestMainEntryPoint:
    """Test main() builds a daily context and hands it to the runtime."""

    @staticmethod
    def test_runs_the_daily_job_in_the_requested_mode():
        """Test 'action' hands the daily job and the workflow mode to run_job() and returns its exit code."""
        with patch('yrt.main.runtime.run_job', return_value=0) as run_job:
            assert main.main(['action']) == 0

        assert run_job.call_args.args == (JOB_DAILY, EXE_MODE_ACTION, main.run_daily)

    @staticmethod
    def test_defaults_to_local_mode():
        """Test no argument means local mode (token files, progress bars)."""
        with patch('yrt.main.runtime.run_job', return_value=0) as run_job:
            main.main([])

        assert run_job.call_args.args == (JOB_DAILY, EXE_MODE_LOCAL, main.run_daily)

    @staticmethod
    def test_invalid_mode_exits():
        """Test an unknown mode exits with the argparse usage error."""
        with pytest.raises(SystemExit):
            main.main(['bogus'])

    @staticmethod
    def test_handles_tracker_errors(tmp_path, monkeypatch, quota_tracker, log_lines):
        """Test a YouTubeTrackerError raised while bootstrapping is logged as fatal and mapped to exit code 1."""
        monkeypatch.setattr(paths, 'HISTORY_LOG', tmp_path / 'history.log')
        monkeypatch.setattr(paths, 'LAST_EXE_LOG', tmp_path / 'last_exe.log')

        with patch('yrt.main.youtube.create_service_local', side_effect=CredentialsError('no token')):
            assert main.main([]) == 1

        lines = log_lines(tmp_path / 'history.log')
        assert lines[0] == PROCESS_START_MARKER
        assert lines[-2] == 'Fatal error: no token'
        assert lines[-1].startswith('Quota spent: 0 units')
        assert not (tmp_path / 'last_exe.log').exists()


@pytest.mark.integration
class TestLastExeLog:
    """Test the last-exe log follows the outcome of a full local run."""

    @staticmethod
    def test_rewritten_on_success(tmp_path, monkeypatch, quota_tracker, daily_config, youtube_mocks, log_lines):
        """Test a successful run ends with the end marker and refreshes last_exe.log with the whole run."""
        monkeypatch.setattr(paths, 'HISTORY_LOG', tmp_path / 'history.log')
        monkeypatch.setattr(paths, 'LAST_EXE_LOG', tmp_path / 'last_exe.log')

        with (
            patch('yrt.main.youtube.create_service_local', return_value=MagicMock()),
            patch('yrt.main.youtube.encode_key'),
        ):
            assert main.main([]) == 0

        lines = log_lines(tmp_path / 'last_exe.log')
        assert lines[0] == PROCESS_START_MARKER
        assert lines[-1] == PROCESS_END_MARKER

    @staticmethod
    def test_kept_when_the_job_fails(tmp_path, monkeypatch, quota_tracker, daily_config, youtube_mocks, log_lines):
        """Test a failing run leaves last_exe.log untouched so the next run re-scans the missed window."""
        monkeypatch.setattr(paths, 'HISTORY_LOG', tmp_path / 'history.log')
        monkeypatch.setattr(paths, 'LAST_EXE_LOG', tmp_path / 'last_exe.log')
        previous_run = f'2024-01-01 00:00:00+0000 [INFO] - {PROCESS_START_MARKER}\n'
        (tmp_path / 'last_exe.log').write_text(previous_run, encoding='utf-8')
        youtube_mocks['add_api_fail'].side_effect = APIError('quota wall')

        with patch('yrt.main.youtube.create_service_local', return_value=MagicMock()):
            assert main.main([]) == 1

        assert (tmp_path / 'last_exe.log').read_text(encoding='utf-8') == previous_run
        assert 'Fatal error: quota wall' in log_lines(tmp_path / 'history.log')


@pytest.mark.integration
class TestRunDaily:
    """Test run_daily() orchestration against patched youtube functions."""

    @staticmethod
    def test_no_new_videos(exec_context, session, daily_config, youtube_mocks, log_lines):
        """Test an empty discovery still updates stats, fills Release Radar and runs both cleanups with the context."""
        main.run_daily(exec_context, session)

        assert 'No addition to perform.' in log_lines(exec_context.history_path)
        youtube_mocks['add_api_fail'].assert_called_once_with(service=session.service, prog_bar=False)
        youtube_mocks['iter_channels'].assert_called_once_with(
            session.service, [MUSIC_CHANNEL], exec_context, daily_config.add_on, prog_bar=False
        )
        assert youtube_mocks['weekly_stats'].call_count == 4
        assert youtube_mocks['weekly_stats'].call_args.kwargs['ref_date'].tzinfo == dt.UTC
        youtube_mocks['add_stats'].assert_not_called()
        youtube_mocks['fill_release_radar'].assert_called_once_with(
            session.service,
            daily_config.playlists['release'].id,
            daily_config.playlists['re_listening'].id,
            daily_config.playlists['legacy'].id,
            exec_context,
            prog_bar=False,
        )
        youtube_mocks['cleanup_expired_videos'].assert_called_once_with(
            session.service, daily_config.playlists, exec_context, prog_bar=False
        )
        youtube_mocks['cleanup_ended_streams'].assert_called_once_with(
            session.service, daily_config.playlists, prog_bar=False
        )
        assert paths.STATS_CSV.exists()

    @staticmethod
    def test_new_video_is_stored_and_routed(exec_context, session, daily_config, youtube_mocks, log_lines):
        """Test a discovered music video is written to stats.csv and added to Release Radar."""
        youtube_mocks['iter_channels'].return_value = [
            PlaylistItem(
                video_id='vid0000001',
                video_title='Title',
                item_id='item_vid0000001',
                release_date=dt.datetime(2024, 1, 15, 12, tzinfo=dt.UTC),
                status='public',
                channel_id=MUSIC_CHANNEL,
                channel_name='Music',
                source_channel_id=MUSIC_CHANNEL,
            )
        ]
        youtube_mocks['add_stats'].return_value = _new_video_frame('vid0000001')

        main.run_daily(exec_context, session)

        lines = log_lines(exec_context.history_path)
        assert 'Add statistics for 1 video(s).' in lines
        assert 'Addition to "Release Radar": 1 video(s).' in lines
        youtube_mocks['add_to_playlist'].assert_called_once_with(
            session.service, daily_config.playlists['release'].id, ['vid0000001'], prog_bar=False
        )
        stored = pd.read_csv(paths.STATS_CSV)
        assert stored['video_id'].tolist() == ['vid0000001']
