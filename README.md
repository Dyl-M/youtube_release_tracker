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

This project follows up the developments made in
the [Automated YouTube Playlist](https://github.com/Dyl-M/auto_youtube_playlist)
project, evolving on a smaller panel of YouTube channels with fewer fluctuations.

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
├── _tests        # Pytest test suite, fixtures and shared configuration
└── yrt           # Main application package (source code)
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