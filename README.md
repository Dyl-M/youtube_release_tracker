# YouTube Release Tracker

[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue?style=flat-square&logo=python&logoColor=white)](https://www.python.org/)
[![uv](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/uv/main/assets/badge/v0.json&style=flat-square)](https://github.com/astral-sh/uv)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json&style=flat-square)](https://github.com/astral-sh/ruff)
[![License](https://img.shields.io/github/license/Dyl-M/youtube_release_tracker?style=flat-square)](LICENSE)

![Status](https://img.shields.io/badge/status-active-brightgreen?style=flat-square)
[![Test & Coverage](https://img.shields.io/github/actions/workflow/status/Dyl-M/youtube_release_tracker/test-coverage.yml?label=Test%20%26%20Coverage&style=flat-square&logo=github-actions&logoColor=white)](https://github.com/Dyl-M/youtube_release_tracker/actions/workflows/test-coverage.yml)
[![DeepSource](https://app.deepsource.com/gh/Dyl-M/youtube_release_tracker.svg/?label=active+issues&show_trend=true&token=WpKQsgGZsHi_FrteJ2YyUhQ_)](https://app.deepsource.com/gh/Dyl-M/youtube_release_tracker/)
[![DeepSource](https://app.deepsource.com/gh/Dyl-M/youtube_release_tracker.svg/?label=code+coverage&show_trend=true&token=WpKQsgGZsHi_FrteJ2YyUhQ_)](https://app.deepsource.com/gh/Dyl-M/youtube_release_tracker/)

![Repository illustration](_media/repo_illustration.png?raw=true "Repository illustration")

A YouTube project able to track the latest video releases among my subscriptions. The videos will be added to specific
playlists based on channel categories.

**Music Playlists:**

- [🚨 BANGER RADAR](https://www.youtube.com/playlist?list=PLOMUdQFdS-XOI8OIWV_Gx-SRhlCS9PKLn): music releases among a
  selection of favorite music channels.
- [📡 RELEASE RADAR](https://www.youtube.com/playlist?list=PLOMUdQFdS-XNpAVOwJ52c_U94kd0rannK): regular music releases
  among my subscriptions.

**Stream Playlists (with automatic cleanup when stream ends):**

- [🎧🔴 Music Lives](https://www.youtube.com/playlist?list=PLOMUdQFdS-XNaPVSol9qCUJvQvN5hO4hJ): Music radios on YouTube.
- [🍿🔴 My streams](https://www.youtube.com/playlist?list=PLOMUdQFdS-XPxmSrgGQjJg-AH-wEEEx-7) (Private): Streams of
  creators outside the “MUSIQUE” category.

**Category Playlists (with automatic retention-based cleanup):**

- [🧠 Educational content](https://www.youtube.com/playlist?list=PLOMUdQFdS-XNcnepE6JblfefVMq1fpa8N) (Private): learning
  and personal development videos. - 30 days retention
- [🍿🎮 Entertainment & Gaming](https://www.youtube.com/playlist?list=PLOMUdQFdS-XN6_25FjZJuKG6vQ6msi4W6) (Private):
  entertainment and gaming content. - 7 days retention
- [💤 ASMR & Relaxation](https://www.youtube.com/playlist?list=PLOMUdQFdS-XMjwIyrP2skD7RI1Xz-TbJw) (Private):
  relaxation videos, background noise and stress relief. - 10 days retention

This project follows up the developments made in
the [Automated YouTube Playlist](https://github.com/Dyl-M/auto_youtube_playlist)
project, evolving on a smaller panel of YouTube channels with fewer fluctuations. The livestream and mixes playlists
still handled by that project are being brought over here (see `_docs/`).

How it works
-------------

A GitHub Actions workflow runs the process once a day (`uv run python -m yrt.main action`); it can also run locally with
`uv run python -m yrt.main local` using OAuth token files in `_tokens/` (git-ignored).

1. Videos that failed to be added on the previous run (`_config/api_failure.json`) are retried first.
2. Every subscribed channel's upload playlist is scanned for videos published since the last execution.
3. Each video gets its statistics (views, likes, comments, duration, live status, Shorts detection) and is routed to a
   playlist: Shorts are ignored, scheduled streams go to the stream playlists, non-music channels go to their category
   playlist, music channels go to Banger Radar (favorites) or Release Radar - long uploads from music-only channels are
   skipped.
4. Release Radar is topped up from the re-listening and legacy playlists, expired videos are removed from the category
   playlists, and ended streams from the stream playlists.
5. Statistics are stored in `_data/stats.csv` and refreshed 1, 4, 12 and 24 weeks after each release.

Every YouTube Data API call goes through a shared retry layer: transient failures (backend errors, connection errors,
timeouts, non-JSON 5xx pages) are retried with exponential backoff, permanent ones are logged and skipped, and quota
rejections are saved to `_config/api_failure.json` for the next run. A quota tracker counts the units spent (1 per
list call, 50 per insert/update/delete) and the run ends with a `Quota spent: N units (...)` line in the log.

Configuration
-------------

All configuration lives in `_config/`:

- `pocket_tube.json` - subscribed channel IDs grouped by category (`MUSIQUE`, `APPRENTISSAGE`, `DIVERTISSEMENT`,
  `GAMING`, `ASMR`), exported from PocketTube.
- `playlists.json` - target playlists with their ID, name and description; category playlists carry `retention_days`,
  stream playlists may carry `cleanup_on_end`.
- `add-on.json` - `favorites` (channels routed to Banger Radar), `playlistNotFoundPass` (channels whose missing upload
  playlist is not worth a warning) and `toPass` (channels skipped entirely).
- `api_failure.json` - videos whose addition failed on quota or unknown errors, replayed on the next run; entries are
  created automatically for any playlist missing from the file.
- `constants.json` (optional) - tunables with sensible defaults; values are validated at start-up and an out-of-range
  value stops the run with a clear message:

```json
{
  "api": {
    "batch_size": 50,
    "max_retries": 3,
    "base_delay_seconds": 1,
    "max_backoff_seconds": 32,
    "daily_quota": 10000
  },
  "network": {
    "timeout_seconds": 5
  },
  "quota": {
    "daily_job_budget": 7000,
    "updates_job_budget": 2500
  },
  "playlists": {
    "release_radar_target_size": 40,
    "relistening_age_weeks": 1
  },
  "video": {
    "long_video_threshold_minutes": 10
  },
  "stats": {
    "week_deltas": [1, 4, 12, 24]
  }
}
```

Development
-------------

The project uses [uv](https://github.com/astral-sh/uv) and Python 3.12+.

```bash
uv sync --extra dev                                   # install with dev dependencies
uv run pytest _tests/ -v                              # test suite (no network, no quota)
uv run pytest _tests/ --cov=yrt --cov-report=term      # with coverage
uv run ruff check . && uv run ruff format --check .   # lint and formatting
uv run mypy yrt/                                      # type checking
uv run python _scripts/sort_db.py                     # sort the channel database
uv run python _scripts/archive_data.py                # archive data older than 6 months
```

Repository structure
-------------

```
youtube_release_tracker/
├── .github       # GitHub Actions workflows, issue templates and Dependabot config
├── _config       # JSON configuration: channels, playlists, favorites and constants
├── _data         # Historical video statistics (stats.csv)
├── _docs         # Project documentation and notes
├── _log          # Execution logs (history.log, last_exe.log)
├── _media        # Repository illustration and media assets
├── _notebooks    # Reporting Jupyter notebooks and exported PDFs
├── _scripts      # Standalone maintenance scripts (database sort, data archiving)
├── _tests        # Pytest test suite, API response fixtures and shared configuration
└── yrt           # Main application package (source code)
    └── youtube   # YouTube API layer: auth, API calls, retry/quota, playlists, stats, cleanup
```

Branches
-------------

- `main`: clean code reference (this branch). Receives code changes and a single squashed execution-log commit per
  month.
- `run`: execution branch where the daily automated process runs and commits its logs and statistics.
- `dev`: integration branch for ongoing development.

External information
-------------

Codes are reviewed by the [DeepSource](https://deepsource.io/) bot.