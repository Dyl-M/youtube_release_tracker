# YouTube Release Tracker

[![GitHub last commit](https://img.shields.io/github/last-commit/Dyl-M/youtube_release_tracker?label=Last%20commit&style=flat-square)](https://github.com/Dyl-M/youtube_release_tracker/commits/main)
[![GitHub commit activity](https://img.shields.io/github/commit-activity/w/Dyl-M/youtube_release_tracker?label=Commit%20activity&style=flat-square)](https://github.com/Dyl-M/youtube_release_tracker/commits/main)
[![DeepSource](https://deepsource.io/gh/Dyl-M/youtube_release_tracker.svg/?label=active+issues&token=w_aZJJfhd5HPPLyXnDJkstmn)](https://deepsource.io/gh/Dyl-M/youtube_release_tracker/?ref=repository-badge)
[![DeepSource](https://deepsource.io/gh/Dyl-M/youtube_release_tracker.svg/?label=resolved+issues&token=w_aZJJfhd5HPPLyXnDJkstmn)](https://deepsource.io/gh/Dyl-M/youtube_release_tracker/?ref=repository-badge)

[![Bluesky followers](https://img.shields.io/bluesky/followers/dyl-m.bsky.social?label=Bluesky)](https://bsky.app/profile/dyl-m.bsky.social)

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
├── .github
│   ├── ISSUE_TEMPLATE
│   │   ├── feature_request.yml
│   │   └── issue_report.yml
│   ├── workflows
│   │   ├── claude.yml
│   │   ├── licence_workflow.yml
│   │   └── main_workflow.yml
│   └── dependabot.yml
│
├── _config
│   ├── add-on.json
│   ├── api_failure.json
│   ├── constants.json
│   ├── playlists.json
│   └── pocket_tube.json
│
├── _data
│   └── stats.csv
│
├── _docs
│   ├── IMPROVEMENTS-2026.md
│   └── notes.txt
│
├── _log
│   ├── history.log
│   └── last_exe.log
│
├── _media
│   └── repo_illustration.png
│
├── _notebooks
│   └── channels_reporting.ipynb
│
├── _scripts
│   ├── __init__.py
│   ├── archive_data.py
│   └── sort_db.py
│
├── _tests
│   ├── fixtures
│   │   ├── sample_playlist_response.json
│   │   └── sample_video_stats.json
│   ├── __init__.py
│   ├── conftest.py
│   ├── README.md
│   ├── test_config.py
│   ├── test_exceptions.py
│   ├── test_file_utils.py
│   ├── test_main.py
│   ├── test_paths.py
│   └── test_youtube.py
│
├── yrt
│   ├── __init__.py
│   ├── analytics.py
│   ├── config.py
│   ├── exceptions.py
│   ├── file_utils.py
│   ├── main.py
│   ├── paths.py
│   └── youtube.py
│
├── .deepsource.toml
├── .gitignore
├── LICENSE
├── pyproject.toml
├── pytest.ini
├── README.md
└── uv.lock
```

External information
-------------

Codes are reviewed by the [DeepSource](https://deepsource.io/) bot.