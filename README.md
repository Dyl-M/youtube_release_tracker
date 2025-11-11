# YouTube Release Tracker

[![GitHub last commit](https://img.shields.io/github/last-commit/Dyl-M/youtube_release_tracker?label=Last%20commit&style=flat-square)](https://github.com/Dyl-M/youtube_release_tracker/commits/main)
[![GitHub commit activity](https://img.shields.io/github/commit-activity/w/Dyl-M/youtube_release_tracker?label=Commit%20activity&style=flat-square)](https://github.com/Dyl-M/youtube_release_tracker/commits/main)
[![DeepSource](https://deepsource.io/gh/Dyl-M/youtube_release_tracker.svg/?label=active+issues&token=w_aZJJfhd5HPPLyXnDJkstmn)](https://deepsource.io/gh/Dyl-M/youtube_release_tracker/?ref=repository-badge)
[![DeepSource](https://deepsource.io/gh/Dyl-M/youtube_release_tracker.svg/?label=resolved+issues&token=w_aZJJfhd5HPPLyXnDJkstmn)](https://deepsource.io/gh/Dyl-M/youtube_release_tracker/?ref=repository-badge)

[![Twitter Follow](https://img.shields.io/twitter/follow/dyl_m_tweets?label=%40dyl_m_tweets&style=social)](https://twitter.com/dyl_m_tweets)
[![Twitch Status](https://img.shields.io/twitch/status/dyl_m_?logo=twitch&label=dyl_m_)](https://www.twitch.tv/dyl_m_)
[![Reddit User Karma](https://img.shields.io/reddit/user-karma/link/dyl_m?label=u%2Fdyl_m&style=social)](https://www.reddit.com/user/Dyl_M)

![Repository illustration](media/repo_illustration.png?raw=true "Repository illustration")

A YouTube project able to track the latest video releases among my subscriptions. The videos will be added to 3 
specific playlist

- [🚨 BANGER RADAR](https://www.youtube.com/playlist?list=PLOMUdQFdS-XOI8OIWV_Gx-SRhlCS9PKLn): music releases among a 
  selection of music channels.
- [📡 RELEASE RADAR](https://www.youtube.com/playlist?list=PLOMUdQFdS-XNpAVOwJ52c_U94kd0rannK): regular music releases 
  among my subscriptions.
- [⏳ Watch Later 2K24](https://www.youtube.com/playlist?list=PLOMUdQFdS-XPfjAeBp5TuNDQmMoiJHdvB) (Private): other type of video to Watch Later (since regular Watch Later playlist can't be 
  manipulated with the API).

This project follows up the developments made in the [Automated YouTube Playlist](https://github.com/Dyl-M/auto_youtube_playlist) 
project, evolving on a smaller panel of YouTube channels with fewer fluctuations.

Repository structure
-------------

Elements followed by `(IGNORED)` are kept ignored / hidden by git for privacy purpose or for being useless for code
comprehension or workflow execution.

```
├── .github
│   ├── ISSUE_TEMPLATE
│   │   ├── feature_request.yml
│   │   └── issue_report.yml
│   ├── workflows
│   │   ├── licence_workflow.yml
│   │   └── main_workflow.yml
│   └── dependabot.yml
│
├── archive (IGNORED)
│
├── data
│   ├── add-on.json
│   ├── api_failure.json
│   ├── playlists.json
│   ├── pocket_tube.json
│   └── stats.csv
│
├── log
│   ├── history.log
│   └── last_exe.log
│
├── media
│
├── notebooks
│   └── channel_reporting.ipynb
│
├── src
│   ├── _sandbox.py
│   ├── analytics.py
│   ├── deprecated_functions.py
│   ├── file_utils.py
│   ├── main.py
│   └── youtube.py
│
├── tokens (IGNORED)
│
├── .deepsource.toml
├── .gitignore
├── CLAUDE.md
├── IMPROVEMENTS.md
├── LICENSE
├── notes.txt
├── README.md
└── requirements.txt
```

External information
-------------

Codes are reviewed by the [DeepSource](https://deepsource.io/) bot.