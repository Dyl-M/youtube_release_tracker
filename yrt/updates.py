"""Frequent job of YouTube Release Tracker: music lives (mixes join it in the port plan's Phase 5).

Importing this module has no side effect; `python -m yrt.updates [local|action]` runs the job through yrt.runtime.
"""

# Standard library
import datetime as dt
import sys
from collections.abc import Sequence

# Local
from . import config, runtime, youtube
from .constants import JOB_UPDATES
from .context import ExecutionContext
from .exceptions import QuotaExhaustedError


def run_updates(ctx: ExecutionContext, session: runtime.Session) -> None:
    """The frequent job: detect the live and upcoming streams of the music channels and update the lives playlist.

    A quota rejection stops the job's work without failing the run: the next slot starts over.

    Args:
        ctx: Execution context of the run.
        session: Session opened by runtime.bootstrap().
    """
    cfg = runtime.load_config()
    service, logger, prog_bar = session.service, session.logger, ctx.prog_bar

    channels = cfg.updates_channels
    stale_before = ctx.now - dt.timedelta(hours=config.LIVES_UPCOMING_GRACE_HOURS)
    logger.info('Live stream detection for %s YouTube channels.', len(channels))

    try:
        lives = youtube.find_live_streams(
            service, channels, stale_before=stale_before, to_pass=cfg.add_on.to_pass, prog_bar=prog_bar
        )
        logger.info('%s live or upcoming stream(s) found.', len(lives))
        youtube.update_lives_playlist(
            service,
            cfg.playlists['music_lives'].id,
            lives,
            stale_before=stale_before,
            max_per_channel=config.LIVES_MAX_PER_CHANNEL,
            prog_bar=prog_bar,
        )

    except QuotaExhaustedError as error:
        logger.warning('Quota exhausted, lives update stopped: %s', error)


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point of the frequent job.

    Args:
        argv: Command-line arguments without the program name (defaults to sys.argv[1:]).

    Returns:
        Process exit code (0 on success, 1 on a handled fatal error).
    """
    exe_mode = runtime.parse_exe_mode(argv, prog='python -m yrt.updates')
    return runtime.run_job(JOB_UPDATES, exe_mode, run_updates)


if __name__ == '__main__':
    sys.exit(main())
