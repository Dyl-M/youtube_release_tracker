"""Tests for yrt/runtime.py - CLI parsing, configuration loading and the bootstrap / finalize / run_job lifecycle."""

# Standard library
import json
from typing import Any
from unittest.mock import MagicMock, patch

# Third-party
import github
import pytest

# Local
from yrt import paths, runtime
from yrt.constants import EXE_MODE_ACTION, EXE_MODE_LOCAL, JOB_DAILY, PROCESS_END_MARKER, PROCESS_START_MARKER
from yrt.exceptions import APIError, ConfigurationError, GitHubError
from yrt.models import AddOnConfig, AppConfig, PlaylistConfig
from yrt.youtube import utils

PLAYLIST_KEYS = runtime.REQUIRED_PLAYLISTS


def _playlists_json():
    """Build a playlists.json body with every required key, one retention rule and one stream cleanup flag."""
    data: dict[str, dict[str, Any]] = {
        key: {'name': f'Playlist {key}', 'description': '', 'id': f'PL{key:0<32}'[:34], 'failed': [], 'pending': []}
        for key in PLAYLIST_KEYS
    }
    data['apprentissage']['retention_days'] = 30
    data['regular_streams']['cleanup_on_end'] = True
    return data


@pytest.fixture
def config_files(tmp_path, monkeypatch):
    """Point the three config paths at temp files with a minimal, valid content; returns the temp directory."""

    def _write(name, data):
        """Write a JSON config file into the temp directory and redirect the matching paths constant."""
        file_path = tmp_path / name
        file_path.write_text(json.dumps(data), encoding='utf-8')
        return file_path

    monkeypatch.setattr(
        paths,
        'POCKET_TUBE_JSON',
        _write(
            'pocket_tube.json',
            {
                'MUSIQUE': ['UCmusic0000000000000000', 'UCboth00000000000000000'],
                'APPRENTISSAGE': ['UClearn0000000000000000'],
                'DIVERTISSEMENT': [],
                'GAMING': ['UCboth00000000000000000'],
            },
        ),
    )
    monkeypatch.setattr(paths, 'PLAYLISTS_JSON', _write('playlists.json', _playlists_json()))
    monkeypatch.setattr(
        paths,
        'ADD_ON_JSON',
        _write(
            'add-on.json',
            {'favorites': {'Fav': 'UCfav000000000000000000'}, 'toPass': ['UCskip00000000000000000']},
        ),
    )
    return tmp_path


@pytest.mark.unit
class TestParseExeMode:
    """Test parse_exe_mode() argparse contract."""

    @staticmethod
    def test_defaults_to_local():
        """Test no argument means local mode."""
        assert runtime.parse_exe_mode([]) == EXE_MODE_LOCAL

    @staticmethod
    def test_action_mode():
        """Test the workflow passes 'action'."""
        assert runtime.parse_exe_mode(['action']) == EXE_MODE_ACTION

    @staticmethod
    def test_unknown_mode_exits():
        """Test a typo no longer silently runs in workflow mode: argparse exits with code 2."""
        with pytest.raises(SystemExit) as exc_info:
            runtime.parse_exe_mode(['bogus'])

        assert exc_info.value.code == 2


@pytest.mark.unit
class TestLoadConfig:
    """Test load_config() builds an AppConfig from the three JSON files."""

    @staticmethod
    def test_loads_pocket_tube(config_files):
        """Test channel categories are loaded and all_channels de-duplicates cross-category channels."""
        cfg = runtime.load_config()

        assert isinstance(cfg, AppConfig)
        assert cfg.music_channels == ['UCmusic0000000000000000', 'UCboth00000000000000000']
        assert sorted(cfg.all_channels) == [
            'UCboth00000000000000000',
            'UClearn0000000000000000',
            'UCmusic0000000000000000',
        ]

    @staticmethod
    def test_loads_playlists(config_files):
        """Test every playlist becomes a PlaylistConfig with its optional rules; queue keys are ignored."""
        cfg = runtime.load_config()

        assert set(cfg.playlists) == set(PLAYLIST_KEYS)
        assert isinstance(cfg.playlists['release'], PlaylistConfig)
        assert cfg.playlists['apprentissage'].retention_days == 30
        assert cfg.playlists['regular_streams'].cleanup_on_end is True
        assert cfg.playlists['release'].retention_days is None

    @staticmethod
    def test_loads_add_on(config_files):
        """Test add-on lists are loaded with defaults for the missing keys."""
        cfg = runtime.load_config()

        assert cfg.add_on == AddOnConfig(
            favorites={'Fav': 'UCfav000000000000000000'}, to_pass=['UCskip00000000000000000']
        )

    @staticmethod
    def test_missing_required_playlist_raises(config_files):
        """Test a playlists.json without a required key raises ConfigurationError."""
        data = _playlists_json()
        del data['banger']
        (config_files / 'playlists.json').write_text(json.dumps(data), encoding='utf-8')

        with pytest.raises(ConfigurationError, match='banger'):
            runtime.load_config()


@pytest.mark.unit
class TestGetGitHubTarget:
    """Test get_github_target() reads the workflow environment."""

    @staticmethod
    def test_reads_both_variables(monkeypatch):
        """Test the repository slug and the token are returned."""
        monkeypatch.setenv('GITHUB_REPOSITORY', 'owner/repo')
        monkeypatch.setenv('PAT', 'token')

        assert runtime.get_github_target() == runtime.GitHubTarget(repo='owner/repo', pat='token')

    @staticmethod
    def test_missing_variable_raises(monkeypatch):
        """Test a missing PAT raises ConfigurationError naming it."""
        monkeypatch.setenv('GITHUB_REPOSITORY', 'owner/repo')
        monkeypatch.delenv('PAT', raising=False)

        with pytest.raises(ConfigurationError, match='PAT'):
            runtime.get_github_target()

    @staticmethod
    def test_empty_variable_raises(monkeypatch):
        """Test an empty repository slug is treated as missing."""
        monkeypatch.setenv('GITHUB_REPOSITORY', '')
        monkeypatch.setenv('PAT', 'token')

        with pytest.raises(ConfigurationError, match='GITHUB_REPOSITORY'):
            runtime.get_github_target()


@pytest.mark.unit
class TestBootstrap:
    """Test bootstrap() opens the loggers and creates the service per execution mode."""

    @staticmethod
    def test_action_mode(exec_context, monkeypatch, log_lines):
        """Test workflow mode uses base64 credentials and carries the GitHub target and creds in the session."""
        monkeypatch.setenv('GITHUB_REPOSITORY', 'owner/repo')
        monkeypatch.setenv('PAT', 'token')
        service = MagicMock()
        before = utils.history

        with patch('yrt.runtime.youtube.create_service_workflow', return_value=(service, 'b64creds')) as create:
            session = runtime.bootstrap(exec_context)

        create.assert_called_once_with()
        assert session.service is service
        assert session.creds_b64 == 'b64creds'
        assert session.github == runtime.GitHubTarget(repo='owner/repo', pat='token')
        assert log_lines(exec_context.history_path) == [PROCESS_START_MARKER]
        assert utils.history is not before  # the youtube package now logs to the job's file

    @staticmethod
    def test_local_mode(exec_context, log_lines):
        """Test local mode uses the token files and has nothing to write back."""
        local_context = runtime.ExecutionContext(**{**vars(exec_context), 'exe_mode': EXE_MODE_LOCAL})
        service = MagicMock()

        with patch('yrt.runtime.youtube.create_service_local', return_value=service) as create:
            session = runtime.bootstrap(local_context)

        create.assert_called_once_with()
        assert session.service is service
        assert session.creds_b64 is None
        assert session.github is None
        assert log_lines(local_context.history_path) == [PROCESS_START_MARKER]

    @staticmethod
    def test_action_mode_without_secrets_fails_before_any_service(exec_context, monkeypatch):
        """Test a missing PAT raises before the service (and its quota) is touched."""
        monkeypatch.delenv('GITHUB_REPOSITORY', raising=False)
        monkeypatch.delenv('PAT', raising=False)

        with (
            patch('yrt.runtime.youtube.create_service_workflow') as create,
            pytest.raises(ConfigurationError, match='GITHUB_REPOSITORY'),
        ):
            runtime.bootstrap(exec_context)

        create.assert_not_called()


@pytest.mark.unit
class TestFinalize:
    """Test finalize() persists credentials, logs the wrap-up lines and refreshes the last-exe log."""

    @staticmethod
    def test_local_mode_encodes_both_token_files(exec_context, session_factory):
        """Test local mode re-encodes credentials.json and oauth.json."""
        local_context = runtime.ExecutionContext(**{**vars(exec_context), 'exe_mode': EXE_MODE_LOCAL})
        session = session_factory(mark_started=True)  # same history file as exec_context

        with patch('yrt.runtime.youtube.encode_key') as encode_key:
            runtime.finalize(local_context, session)

        assert [call.kwargs['json_path'] for call in encode_key.call_args_list] == [
            str(paths.CREDENTIALS_JSON),
            str(paths.OAUTH_JSON),
        ]

    @staticmethod
    def test_action_mode_updates_the_secret(exec_context, session_factory):
        """Test workflow mode writes the credentials back to the repository secret."""
        target = runtime.GitHubTarget(repo='owner/repo', pat='token')
        session = session_factory(mark_started=True, creds_b64='b64creds', target=target)

        with patch('yrt.runtime.github.Github') as github_cls:
            runtime.finalize(exec_context, session)

        github_cls.return_value.get_repo.assert_called_once_with('owner/repo')
        github_cls.return_value.get_repo.return_value.create_secret.assert_called_once_with('CREDS_B64', 'b64creds')

    @staticmethod
    def test_action_mode_without_creds_skips_the_secret(exec_context, session_factory):
        """Test nothing is written back when the session carries no credentials."""
        session = session_factory(mark_started=True, creds_b64=None, target=runtime.GitHubTarget(repo='o/r', pat='t'))

        with patch('yrt.runtime.github.Github') as github_cls:
            runtime.finalize(exec_context, session)

        github_cls.assert_not_called()

    @staticmethod
    def test_logs_summary_then_end_marker_and_writes_last_exe(exec_context, quota_tracker, log_lines, session_factory):
        """Test the quota summary precedes the end marker and the last-exe log holds the whole run."""
        session = session_factory(mark_started=True, target=runtime.GitHubTarget(repo='o/r', pat='t'))

        runtime.finalize(exec_context, session)

        lines = log_lines(exec_context.history_path)
        assert lines[0] == PROCESS_START_MARKER
        assert lines[-2].startswith('Quota spent: 0 units')
        assert lines[-1] == PROCESS_END_MARKER
        assert log_lines(exec_context.last_exe_path) == lines


@pytest.mark.unit
class TestUpdateRepoSecrets:
    """Test update_repo_secrets() through a patched PyGithub client."""

    @staticmethod
    def test_success_is_logged():
        """Test the secret is created and the success is logged."""
        logger = MagicMock()
        target = runtime.GitHubTarget(repo='owner/repo', pat='token')

        with patch('yrt.runtime.github.Github') as github_cls:
            runtime.update_repo_secrets(target, 'CREDS_B64', 'value', logger)

        github_cls.return_value.get_repo.return_value.create_secret.assert_called_once_with('CREDS_B64', 'value')
        logger.info.assert_called_once()

    @staticmethod
    def test_github_failure_raises_github_error():
        """Test a PyGithub exception is logged and re-raised as GitHubError."""
        logger = MagicMock()
        target = runtime.GitHubTarget(repo='owner/repo', pat='token')

        with patch('yrt.runtime.github.Github') as github_cls:
            github_cls.return_value.get_repo.return_value.create_secret.side_effect = github.GithubException(403, 'no')
            with pytest.raises(GitHubError, match='CREDS_B64'):
                runtime.update_repo_secrets(target, 'CREDS_B64', 'value', logger)

        logger.error.assert_called_once()


@pytest.mark.unit
class TestCopyLastExeLog:
    """Test copy_last_exe_log() extracts the most recent run."""

    @staticmethod
    def test_keeps_only_the_last_run(tmp_path, log_lines):
        """Test a history holding two runs yields the second one, from its start marker to the end."""
        history = tmp_path / 'history.log'
        last_exe = tmp_path / 'last_exe.log'
        history.write_text(
            f'2024-01-01 00:00:00+0000 [INFO] - {PROCESS_START_MARKER}\n'
            f'2024-01-01 00:00:01+0000 [INFO] - old\n'
            f'2024-01-02 00:00:00+0000 [INFO] - {PROCESS_START_MARKER}\n'
            f'2024-01-02 00:00:01+0000 [INFO] - new\n',
            encoding='utf-8',
        )

        runtime.copy_last_exe_log(history, last_exe)

        assert log_lines(last_exe) == [PROCESS_START_MARKER, 'new']

    @staticmethod
    def test_history_without_marker_raises(tmp_path):
        """Test a history log without any start marker raises ValueError."""
        history = tmp_path / 'history.log'
        history.write_text('2024-01-01 00:00:00+0000 [INFO] - nothing\n', encoding='utf-8')

        with pytest.raises(ValueError, match=PROCESS_START_MARKER):
            runtime.copy_last_exe_log(history, tmp_path / 'last_exe.log')


@pytest.fixture
def job_files(tmp_path, monkeypatch):
    """Redirect the daily job's log files under tmp_path; returns (history, last_exe)."""
    history, last_exe = tmp_path / 'history.log', tmp_path / 'last_exe.log'
    monkeypatch.setattr(paths, 'HISTORY_LOG', history)
    monkeypatch.setattr(paths, 'LAST_EXE_LOG', last_exe)
    return history, last_exe


@pytest.mark.unit
class TestRunJob:
    """Test run_job() builds the context, drives bootstrap -> body -> finalize and maps errors to exit codes."""

    @staticmethod
    def test_success_returns_zero(job_files, quota_tracker, monkeypatch, log_lines):
        """Test a clean run calls the body with a daily context and the session, then refreshes the last-exe log."""
        history, last_exe = job_files
        monkeypatch.setenv('GITHUB_REPOSITORY', 'owner/repo')
        monkeypatch.setenv('PAT', 'token')
        body = MagicMock()

        with (
            patch('yrt.runtime.youtube.create_service_workflow', return_value=(MagicMock(), 'b64')),
            patch('yrt.runtime.github.Github'),
        ):
            code = runtime.run_job(JOB_DAILY, EXE_MODE_ACTION, body)

        assert code == 0
        ctx, session = body.call_args.args
        assert (ctx.job, ctx.exe_mode, ctx.history_path, ctx.last_exe_path) == (
            JOB_DAILY,
            EXE_MODE_ACTION,
            history,
            last_exe,
        )
        assert isinstance(session, runtime.Session)
        assert log_lines(last_exe)[-1] == PROCESS_END_MARKER

    @staticmethod
    def test_tracker_error_returns_one_and_keeps_last_exe(job_files, quota_tracker, monkeypatch, log_lines):
        """Test a YouTubeTrackerError is logged as fatal with the quota summary; the last-exe log is not rewritten."""
        history, last_exe = job_files
        previous_run = f'2024-01-01 00:00:00+0000 [INFO] - {PROCESS_START_MARKER}\n'
        last_exe.write_text(previous_run, encoding='utf-8')
        monkeypatch.setenv('GITHUB_REPOSITORY', 'owner/repo')
        monkeypatch.setenv('PAT', 'token')
        body = MagicMock(side_effect=APIError('boom'))

        with patch('yrt.runtime.youtube.create_service_workflow', return_value=(MagicMock(), 'b64')):
            code = runtime.run_job(JOB_DAILY, EXE_MODE_ACTION, body)

        assert code == 1
        lines = log_lines(history)
        assert lines[-2] == 'Fatal error: boom'
        assert lines[-1].startswith('Quota spent: 0 units')
        assert PROCESS_END_MARKER not in lines
        assert last_exe.read_text(encoding='utf-8') == previous_run

    @staticmethod
    def test_bootstrap_failure_is_fatal(job_files, quota_tracker, monkeypatch, log_lines):
        """Test a configuration error raised before the service exists is reported the same way."""
        history, _ = job_files
        monkeypatch.delenv('GITHUB_REPOSITORY', raising=False)
        monkeypatch.delenv('PAT', raising=False)
        body = MagicMock()

        code = runtime.run_job(JOB_DAILY, EXE_MODE_ACTION, body)

        assert code == 1
        body.assert_not_called()
        assert any(line.startswith('Fatal error: Required environment variable') for line in log_lines(history))

    @staticmethod
    def test_corrupt_last_exe_log_is_fatal(job_files, quota_tracker, log_lines):
        """Test an unparseable last-exe log is logged as a fatal error instead of escaping as a traceback."""
        history, last_exe = job_files
        last_exe.write_text('garbage\n', encoding='utf-8')
        body = MagicMock()

        code = runtime.run_job(JOB_DAILY, EXE_MODE_LOCAL, body)

        assert code == 1
        body.assert_not_called()
        assert any(line.startswith('Fatal error: Could not parse date') for line in log_lines(history))
