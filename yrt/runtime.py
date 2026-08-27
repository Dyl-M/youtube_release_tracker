"""Process runtime shared by the entry points: CLI parsing, configuration loading, service bootstrap and wrap-up.

A job is `run_job(ctx, body)`: bootstrap (loggers, YouTube service) -> body (the job's own work) -> finalize (secret
refresh, quota summary, last-exe log). Everything the daily and the frequent job have in common lives here.
"""

# Standard library
import argparse
import logging
import os
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

# Third-party
import github
import pyyoutube as pyt

# Local
from . import file_utils, paths, youtube
from .constants import (
    CATEGORY_ENTERTAINMENT,
    CATEGORY_GAMING,
    CATEGORY_LEARNING,
    CATEGORY_MUSIC,
    EXE_MODE_ACTION,
    EXE_MODE_LOCAL,
    EXE_MODES,
    PROCESS_END_MARKER,
    PROCESS_START_MARKER,
)
from .context import ExecutionContext
from .exceptions import ConfigurationError, GitHubError, YouTubeTrackerError
from .logging_utils import create_file_logger
from .models import AddOnConfig, AppConfig, PlaylistConfig
from .youtube import utils

# Name of the GitHub repository secret holding the base64-encoded credentials
CREDS_ENV_NAME = 'CREDS_B64'

# Playlists every job expects in playlists.json
REQUIRED_PLAYLISTS = [
    'release',
    'banger',
    're_listening',
    'legacy',
    'apprentissage',
    'divertissement_gaming',
    'asmr',
    'music_lives',
    'regular_streams',
]

# Channel categories every job expects in pocket_tube.json (ASMR is optional)
REQUIRED_CATEGORIES = [CATEGORY_MUSIC, CATEGORY_LEARNING, CATEGORY_ENTERTAINMENT, CATEGORY_GAMING]


# CLI


def parse_exe_mode(argv: Sequence[str] | None = None, *, prog: str | None = None) -> str:
    """Parse the execution mode from the command line.

    Args:
        argv: Arguments without the program name (defaults to sys.argv[1:]).
        prog: Program name shown in the usage line (e.g. 'python -m yrt.main').

    Returns:
        The execution mode, one of EXE_MODES ('local' when omitted).
    """
    parser = argparse.ArgumentParser(prog=prog, description='YouTube Release Tracker job.')
    parser.add_argument(
        'mode',
        nargs='?',
        choices=EXE_MODES,
        default=EXE_MODE_LOCAL,
        help='local: token files and progress bars (default); action: GitHub Actions credentials, no progress bars',
    )
    args = parser.parse_args(argv)
    mode: str = args.mode
    return mode


# Configuration


def _load_playlists_config() -> dict[str, PlaylistConfig]:
    """Load and parse playlists configuration into PlaylistConfig instances.

    Returns:
        Dictionary mapping playlist keys to PlaylistConfig instances (queue keys are ignored).
    """
    playlists_data = file_utils.load_json(str(paths.PLAYLISTS_JSON), required_keys=REQUIRED_PLAYLISTS)

    return {
        name: PlaylistConfig(
            id=data['id'],
            name=data['name'],
            description=data['description'],
            retention_days=data.get('retention_days'),
            cleanup_on_end=data.get('cleanup_on_end'),
        )
        for name, data in playlists_data.items()
    }


def _load_addon_config() -> AddOnConfig:
    """Load and parse add-on configuration into an AddOnConfig instance.

    Returns:
        AddOnConfig instance with configuration data.
    """
    add_on_data = file_utils.load_json(str(paths.ADD_ON_JSON), required_keys=['favorites'])

    return AddOnConfig(
        favorites=add_on_data['favorites'],
        playlist_not_found_pass=add_on_data.get('playlistNotFoundPass', []),
        to_pass=add_on_data.get('toPass', []),
        certified=add_on_data.get('certified', []),
    )


def load_config() -> AppConfig:
    """Load the three configuration files into an AppConfig.

    Returns:
        The channel categories, the playlist definitions and the add-on lists.

    Raises:
        ConfigurationError: If a file is missing, malformed or lacks a required key.
    """
    pocket_tube = file_utils.load_json(str(paths.POCKET_TUBE_JSON), required_keys=REQUIRED_CATEGORIES)
    return AppConfig(pocket_tube=pocket_tube, playlists=_load_playlists_config(), add_on=_load_addon_config())


# GitHub


@dataclass(frozen=True)
class GitHubTarget:
    """Where the refreshed credentials are written back in workflow mode.

    Attributes:
        repo: Repository slug (owner/name).
        pat: Personal access token allowed to update repository secrets.
    """

    repo: str
    pat: str


def get_github_target() -> GitHubTarget:
    """Read and validate the GitHub environment variables of workflow mode.

    Returns:
        The repository slug and the token.

    Raises:
        ConfigurationError: If GITHUB_REPOSITORY or PAT is missing or empty.
    """
    repo = os.environ.get('GITHUB_REPOSITORY', '')
    pat = os.environ.get('PAT', '')
    missing = [name for name, value in (('GITHUB_REPOSITORY', repo), ('PAT', pat)) if not value]

    if missing:
        raise ConfigurationError(
            f'Required environment variable {" or ".join(missing)} not set or empty. '
            f'Please configure GitHub repository secrets.'
        )

    return GitHubTarget(repo=repo, pat=pat)


def update_repo_secrets(target: GitHubTarget, secret_name: str, new_value: str, logger: logging.Logger) -> None:
    """Update a GitHub repository Secret value.

    Args:
        target: Repository and token.
        secret_name: GitHub repository Secret name.
        new_value: New value for the selected Secret.
        logger: Job logger.

    Raises:
        GitHubError: If the secret update fails.
    """
    repo = github.Github(auth=github.Auth.Token(target.pat)).get_repo(target.repo)
    try:
        repo.create_secret(secret_name, new_value)
        logger.info("Repository Secret '%s' updated successfully.", secret_name)

    except (github.GithubException, ValueError) as error:
        logger.error("Failed to update Repository Secret '%s' : %s", secret_name, error)
        raise GitHubError(f"Failed to update Repository Secret '{secret_name}': {error}") from error


# Job lifecycle


@dataclass(frozen=True)
class Session:
    """What bootstrap() hands to a job body.

    Attributes:
        service: Authenticated YouTube client.
        creds_b64: Base64 credentials to write back to the repository secret (workflow mode only).
        github: Repository and token for the write-back (workflow mode only).
        logger: Job logger writing to the job's history log.
    """

    service: pyt.Client
    creds_b64: str | None
    github: GitHubTarget | None
    logger: logging.Logger


JobBody = Callable[[ExecutionContext, Session], None]


def bootstrap(ctx: ExecutionContext) -> Session:
    """Open the job's loggers and create the YouTube service.

    Args:
        ctx: Execution context of the run.

    Returns:
        The session; its first log line is the process start marker.

    Raises:
        ConfigurationError: If workflow mode lacks the GitHub environment variables.
        CredentialsError: If workflow credentials are missing or cannot be refreshed.
        YouTubeServiceError: If the service creation fails.
    """
    logger = create_file_logger('history_main', ctx.history_path, respect_no_logging=False)
    utils.set_logger(create_file_logger('history', ctx.history_path))  # the youtube package logs to the job's file
    logger.info(PROCESS_START_MARKER)

    if ctx.exe_mode == EXE_MODE_ACTION:
        target = get_github_target()  # fail before spending any quota
        service, creds_b64 = youtube.create_service_workflow()
        return Session(service=service, creds_b64=creds_b64, github=target, logger=logger)

    return Session(service=youtube.create_service_local(), creds_b64=None, github=None, logger=logger)


def copy_last_exe_log(history_path: Path, last_exe_path: Path) -> None:
    """Copy the last run's lines from a history log to the matching last-exe log.

    Args:
        history_path: History log of the job.
        last_exe_path: Last-exe log of the job (overwritten).

    Raises:
        ValueError: If the history log holds no process start marker.
    """
    history = history_path.read_text(encoding='utf8')

    marker_idx = history.rfind(PROCESS_START_MARKER)
    if marker_idx == -1:
        raise ValueError(f'No "{PROCESS_START_MARKER}" line in {history_path}')

    line_start = history.rfind('\n', 0, marker_idx) + 1
    last_exe_path.write_text(history[line_start:], encoding='utf8')


def finalize(ctx: ExecutionContext, session: Session) -> None:
    """Persist credentials, log the quota summary and the end marker, then refresh the last-exe log.

    Args:
        ctx: Execution context of the run.
        session: Session returned by bootstrap().

    Raises:
        GitHubError: If the repository secret cannot be updated.
        FileAccessError: If a local token file is missing.
    """
    if ctx.exe_mode == EXE_MODE_LOCAL:  # Credentials in base64 update - Local option
        youtube.encode_key(json_path=str(paths.CREDENTIALS_JSON))
        youtube.encode_key(json_path=str(paths.OAUTH_JSON))

    elif session.creds_b64 is not None and session.github is not None:
        update_repo_secrets(session.github, CREDS_ENV_NAME, session.creds_b64, session.logger)

    session.logger.info(youtube.quota.get_tracker().summary())  # e.g. "Quota spent: 1234 units (...)"
    session.logger.info(PROCESS_END_MARKER)
    copy_last_exe_log(ctx.history_path, ctx.last_exe_path)  # only reached on success: failed runs keep the marker


def run_job(ctx: ExecutionContext, body: JobBody) -> int:
    """Run a job end to end and translate the outcome into an exit code.

    Args:
        ctx: Execution context of the run.
        body: The job's own work, called between bootstrap() and finalize().

    Returns:
        0 on success, 1 when a YouTubeTrackerError stopped the run (logged as a fatal error with the quota spent).
    """
    top_level = create_file_logger('top_level', ctx.history_path, respect_no_logging=False)

    try:
        session = bootstrap(ctx)
        body(ctx, session)
        finalize(ctx, session)

    except YouTubeTrackerError as error:
        # ConfigurationError, APIError, CredentialsError, GitHubError... - unexpected exceptions keep their traceback
        top_level.critical('Fatal error: %s', error)
        top_level.info(youtube.quota.get_tracker().summary())  # what the failed run still spent
        return 1

    return 0
