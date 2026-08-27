# Port Plan — `auto_youtube_playlist` → `youtube_release_tracker`

Plan to absorb the sister repository [`Dyl-M/auto_youtube_playlist`](https://github.com/Dyl-M/auto_youtube_playlist)
(Music Lives + Mixes playlists, adaptive schedule) into this project, then retire it.

Written 2026-08-27 from a review of the sister repo's failures, its code, and measurements made against the live YouTube
Data API. Figures marked *measured* were observed on that date; everything else is an estimate.

---

## 1. Why now

### 1.1 The sister repo is down

The `Playlists updates` workflow has failed on every run since **2026-08-26 12:27 UTC** (6 consecutive failures at the
time of writing). No GitHub issue was filed because `update_workflow.yml` has no failure→issue step.

Every failure is the same traceback:

```
src/youtube_req.py:332 in find_livestreams
    sections_as_dict = json.loads(js_scripts.replace('var ytInitialData = ', '')[:-1])
json.decoder.JSONDecodeError: Expecting ',' delimiter: line 1 column 795163
```

`find_livestreams()` scrapes `youtube.com/channel/{id}`, extracts the `ytInitialData` JS blob with bs4 and parses it as
JSON. Verified facts:

- Runner environment identical between last success and first failure (Python 3.11.16, beautifulsoup4 4.15.0, same
  dependency set) → not a dependency regression.
- The exact same bs4 code path parses fine from a residential IP → YouTube changed the page variant served to GitHub's
  datacenter IPs. Not reproducible locally, not under our control.
- `JSONDecodeError` is not caught (only `IndexError`/`ConnectionError` are) and `main.py` only catches `ReadTimeout`, so
  one bad channel kills the run **before the Mixes update starts**.

### 1.2 The livestream detection was already broken

From the sister repo's `history.log` (Jun–Aug 2026, 436 runs): **0 livestreams added, 39 removal events**. The
`channelFeaturedContentRenderer` scrape only ever exposed the channel's *featured* live, and stopped surfacing even that
months ago. "Porting the logic" therefore means **replacing** it.

### 1.3 The two repos fight over the same playlist

`music_lives` here (`_config/playlists.json`) and `lives` there are the **same playlist**
(`PLOMUdQFdS-XNaPVSol9qCUJvQvN5hO4hJ`). This repo adds *upcoming* music streams to it (`yrt/router.py`,
`_route_stream`); the sister repo deletes everything whose status is not `'live'`. On a normal day the sister repo
removed what this repo had scheduled. Today nothing cleans the playlist at all (`music_lives` has no
`cleanup_on_end`).

### 1.4 The sister repo's own quota was already saturated

18 `Quota exceeded` events in Jun–Aug, caused by re-sorting the lives playlist on 425 of 436 runs at 50 units per moved
item.

---

## 2. Measured facts (2026-08-27)

| Fact                                                                  | Value                                                                                                                                                                             |
|-----------------------------------------------------------------------|-----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| `search.list(eventType='live')` per channel                           | 100 units × 184 channels = **18,400 units/run → unusable**                                                                                                                        |
| `playlistItems.list('UULV' + channel[2:])` ("Live" tab as a playlist) | 1 unit; Lofi Girl returned **25 items, single page** (23 `live`, 2 `none`, 0 `upcoming`), live items at indices 0–22                                                              |
| `videos.list(part=liveStreamingDetails)`                              | 1 unit / 50 ids; returns `liveBroadcastContent`, `concurrentViewers`, `actualStartTime`, `scheduledStartTime` — sorting data comes with detection                                 |
| `GET /channel/{id}/live` → `<link rel="canonical">`                   | free; `watch?v=…` when a live/upcoming exists, channel URL otherwise; exposes only **one** stream per channel                                                                     |
| RSS `feeds/videos.xml?channel_id=`                                    | free; 15 latest entries, includes live streams; cache lag unknown                                                                                                                 |
| `music_lives` playlist today                                          | 33 items: 32 `live`, 1 `none`                                                                                                                                                     |
| Sort cost today on those 33 items                                     | naive "position differs": 26 moves = 1,300 units; LIS-minimal: 12 moves = 600 units; 20/33 items drifted ≤ 1 rank (viewer jitter)                                                 |
| Mixes volume (`mix_history.csv`, last 35 days)                        | 5.0/day average — Tue 13.4, Thu 6.2, Fri 4.8, Wed 4.0, Mon 3.4, Sat 2.8, Sun 0.2                                                                                                  |
| Lives churn (sister log, last 30 days)                                | ~1.5 removals/day; adds unknown (detection broken)                                                                                                                                |
| Daily job here, heavy day (2026-08-01)                                | 233 channels, 80 videos, 53 inserts, 10 deletes ≈ 3,500–4,000 units                                                                                                               |
| Channel sets                                                          | MUSIQUE 131 (1-channel diff each way between repos); `certified` 53 (52 not in MUSIQUE, already in this repo's `add-on.json`, loaded but unused); sister `toPass` 5 (absent here) |
| Test suite                                                            | 177 passed, 23 skipped, **44 %** line coverage                                                                                                                                    |

---

## 3. Decisions (defaults chosen; change here, not in code)

| #  | Decision                         | Default                                                                                                              | Alternatives                                                                                                         |
|----|----------------------------------|----------------------------------------------------------------------------------------------------------------------|----------------------------------------------------------------------------------------------------------------------|
| D1 | `music_lives` content policy     | **live + upcoming**; remove when `liveBroadcastContent == 'none'` or private; never remove `upcoming`                | live-only (sister behaviour; would require rerouting upcoming music streams)                                         |
| D2 | Per-channel cap on lives         | **unlimited**, with `lives.max_per_channel` config knob (top-k by concurrent viewers)                                | k = 3 halves playlist size and sort cost; global top-N rejected (boundary churn = 100 units per swap)                |
| D3 | Live detection source            | **`UULV` playlist + `videos.list`** (deterministic, ~200 units/run)                                                  | `/live` canonical probe as optional pre-filter (~20 units/run, but HTML served to runners is what just broke)        |
| D4 | Where mixes are discovered       | **frequent job** (with lives), on the adaptive schedule, using its own last-exe window                               | daily job (simpler, but makes the adaptive schedule pointless)                                                       |
| D5 | Sorting cadence                  | ≤ **2 sort slots/day**, LIS-minimal moves, ignore drift < 3 ranks, cap 10 moves/run                                  | sort every run (sister behaviour: ~9,000 units/day)                                                                  |
| D6 | Quota strategy                   | **in-process quota guard** with per-job budgets (daily 7,000 / frequent 2,500 summed over the day)                   | second GCP project for the frequent job (clean per-project quota but ToS grey zone); official quota-extension form   |
| D7 | Adaptive schedule mechanism      | **data on `run`** (`_data/schedule.json`) + hourly cron with an early-exit gate                                      | rewriting workflow cron lines on `main` (sister behaviour) — breaks the `dev` fast-forward invariant on every change |
| D8 | `mix_history.csv`                | **archive** to `_archive/_data/mix_history_2022-2026.csv`; `stats.csv` already tracks these videos                   | keep appending (duplicate of stats)                                                                                  |
| D9 | Hotfix the sister repo meanwhile | **yes, minimal** (catch `JSONDecodeError` per channel, widen `main.py` except) so Mixes keep flowing during the port | let it stay down                                                                                                     |

---

## 4. Target design

### 4.1 Two jobs, one codebase

```
python -m yrt.main action        # DAILY job (unchanged scope)
                                 #   subscriptions → Release/Banger Radar, category playlists,
                                 #   upcoming streams → music_lives / regular_streams,
                                 #   stats.csv, weekly stats, retention cleanup, ended-stream cleanup,
                                 #   + adjust_schedule → _data/schedule.json

python -m yrt.updates action     # FREQUENT job (new, on the adaptive schedule)
                                 #   lives: detect (UULV) → add / remove / (sort in sort slots)
                                 #   mixes: MUSIQUE ∪ certified − toPass, window = its own last-exe
```

Both jobs share: service bootstrap, secrets refresh, quota guard, retry layer, models, router, config.

### 4.2 State split (the trap from IMPROVEMENTS-2026 #10)

`LAST_EXE` is read from `_log/last_exe.log` and rewritten by `copy_last_exe_log()` at the end of every run. If the
frequent job used the same file, the daily job's look-back window would shrink to "since the last lives run" and
silently miss uploads.

| State                      | Daily job                       | Frequent job                                                                           |
|----------------------------|---------------------------------|----------------------------------------------------------------------------------------|
| Last-exe marker            | `_log/last_exe.log` (unchanged) | `_log/updates_last_exe.log`                                                            |
| History log                | `_log/history.log` (unchanged)  | `_log/updates_history.log`                                                             |
| Data commits to `run`      | as today                        | `git pull --rebase origin run` + push with 3 retries                                   |
| `CREDS_B64` secret refresh | as today                        | same code; last writer wins (the refresh token is stable, the access token is a cache) |

`ExecutionContext(now, last_exe, job)` replaces the import-time `NOW` / `LAST_EXE` in `yrt/youtube/utils.py`; the
module-level names stay as thin aliases until every call site is migrated.

### 4.3 Quota guard (IMPROVEMENTS-2026 #8 + #17, generalised)

```
yrt/youtube/retry.py
    @api_call(cost=1 | 50, transient=TRANSIENT_ERRORS)   # backoff + jitter, error triage, quota accounting
yrt/youtube/quota.py
    QuotaTracker(budget).charge(units) / .can_afford(units) / .spent
yrt/exceptions.py
    APIError(message, *, reason=None, status_code=None, video_id=None)
    QuotaExhaustedError(APIError)
```

Every API call goes through `@api_call`; writes (insert/update/delete, 50 units) check `can_afford()` first. Work in
each job is ordered by value — **adds → removals → sorting** — so the guard degrades gracefully: sorting is dropped
first, then removals, and adds spill into `api_failure.json` exactly as today.

### 4.4 Lives (`yrt/youtube/lives.py`)

```
LIVE_TAB_PLAYLIST_PREFIX = 'UULV'                       # constants.py

get_live_candidates(service, channel_id) -> list[str]   # 1 unit; playlistNotFound → []
find_live_streams(service, channels) -> list[LiveStream] # videos.list on candidates, keep 'live' (+ 'upcoming' per D1)
update_lives_playlist(service, playlist_id, lives, *, max_per_channel) -> None
    # fetch current items (paginated), never insert a duplicate (YouTube allows them),
    # insert new lives at their rank via snippet.position, remove 'none' / private
```

`LiveStream` dataclass (`models.py`): `video_id, channel_id, title, status, concurrent_viewers, total_views,
actual_start_time, scheduled_start_time`.

### 4.5 Sorting (`yrt/youtube/lives.py::sort_lives_playlist`)

Rank key: `(concurrent_viewers desc, total_views desc, actual_start_time desc)`.

1. Compute target order; map current positions into target ranks.
2. Longest-increasing-subsequence → the minimal set of items that must move.
3. Drop items whose rank drift is `< lives.sort_drift_threshold` (default 3).
4. Cap at `lives.sort_max_moves` (default 10) per run, highest drift first.
5. One `playlistItems.update` (50 units) per move, through the quota guard.

Runs only when the current schedule slot has `sort: true` (D5).

### 4.6 Mixes

- Router step 5: music channel + long video + music-only → **`mixes`** instead of `ROUTING_NONE`
  (`RouterConfig.mixes_id`, `create_router_from_config`).
- `certified` channels are treated as music channels for routing (`music_channels ∪ certified`).
- `_config/playlists.json`: `mixes` gets `"retention_days": 7` → `cleanup_expired_videos()` handles removal (by *date
  added* rather than the sister's *release date*; equivalent at this cadence).
- Premieres are already excluded upstream (`live_status == 'upcoming'` routes to streams).
- Optional RSS pre-filter (`yrt/youtube/feeds.py::channels_with_new_uploads`) so the frequent job only calls
  `playlistItems.list` for channels whose feed shows an entry newer than its last-exe; the day's first slot always does
  the full pass as a safety net.

### 4.7 Adaptive schedule (D7)

```
_data/schedule.json                      # on `run`, regenerated by the daily job
{
  "generated_at": "2026-09-01T09:12:00+00:00",
  "window_weeks": 5,
  "days": {
    "MON": {"slots": ["00:00", "12:00", "15:00", "18:00", "21:00"], "sort_slots": ["12:00", "18:00"]},
    "TUE": {"slots": ["00:00", "12:00", "14:00", "16:00", "18:00", "20:00", "22:00"], "sort_slots": ["12:00", "18:00"]},
    ...
  }
}
```

- `_scripts/adjust_schedule.py` ports `cron_update.py`: per-weekday mean of mixes released over the last 5 weeks,
  computed from `stats.csv` (MUSIQUE ∪ certified, `duration ≥ long_video_threshold`, not shorts), then the sister's
  `make_update_pattern()` rule (0 → midnight only; n → `12:00` + n evenly spaced slots, max 6). Runs as a step of the
  daily job and is committed with the rest of `_data/`.
- `updates_workflow.yml`: `cron: "0 * * * *"` (UTC, like the sister). First step `python -m yrt.schedule_gate`
  prints `run=true` when a slot falls inside `[now − gate_window, now]` (gate window 90 min, tolerant to GitHub's
  scheduler lag, see IMPROVEMENTS-2026 #20) and `sort=true` when that slot is a sort slot; the rest of the job is
  conditioned on it. Stateless: no commit needed to decide.
- Workflow files never change → `main` stays a pure code branch, `dev` stays fast-forwardable.

### 4.8 Workflow layout after the port

| Workflow                                                | Trigger                          | Branch       | Role                                                      |
|---------------------------------------------------------|----------------------------------|--------------|-----------------------------------------------------------|
| `main_workflow.yml`                                     | daily, 00:00 America/Los_Angeles | `run`        | daily job + `adjust_schedule`                             |
| `updates_workflow.yml` (new)                            | hourly + `workflow_dispatch`     | `run`        | gate → frequent job; failure → issue (same step as daily) |
| `monthly_consolidation.yml`                             | 1st of month                     | `main`/`run` | unchanged (`updates_*.log` files ride along)              |
| `ship.yml`, `test-coverage.yml`, `licence_workflow.yml` | —                                | —            | unchanged                                                 |

---

## 5. Phases

Each phase = one `feat/*` (or `fix/*`) branch off `dev`, squash PR into `dev`, `test` check green. Ship to `main`
by fast-forward when a coherent batch is merged (at least after Phase 3 and after Phase 6). Sizes: S ≤ ½ day, M ≈ 1 day,
L ≈ 2 days.

### Phase 0 — Stop the bleeding (S, sister repo + docs)

| Task                                                                                                                             | Where                       |
|----------------------------------------------------------------------------------------------------------------------------------|-----------------------------|
| Catch `json.JSONDecodeError` per channel in `find_livestreams` (warn + `return []`)                                              | sister `src/youtube_req.py` |
| Widen the lives `except` in `main.py` to `(requests.RequestException, json.JSONDecodeError, KeyError)` so Mixes still update     | sister `src/main.py`        |
| Add a failure→issue step to `update_workflow.yml` (copy from this repo)                                                          | sister `.github/workflows/` |
| Fix `_docs/IMPROVEMENTS-2026.md`: coverage 44 %, duplicate "#15", Phase 2 item 9 wrongly marked done, stale `yrt/youtube.py` row | this repo                   |

Acceptance: sister `Playlists updates` green on the next scheduled run; Mixes additions resume.

### Phase 1 — Foundations (L) · `feat/api-retry-quota`

Covers IMPROVEMENTS-2026 **#8, #17, #9, #14** and a bug.

| Task                                                                                                                                                                                                                                    | Files                                                     |
|-----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|-----------------------------------------------------------|
| `yrt/youtube/retry.py`: `@api_call(cost, transient)` decorator — backoff + jitter, reason normalisation, error triage; `add_to_playlist` / `del_from_playlist` / cleanup fetches / `get_videos` / `get_playlist_items` migrated onto it | `yrt/youtube/{retry,playlist,cleanup,api}.py`             |
| `yrt/youtube/quota.py`: `QuotaTracker` (budget from config, `charge`, `can_afford`, `spent`, summary log line at job end)                                                                                                               | new                                                       |
| `APIError(reason, status_code, video_id)`, `QuotaExhaustedError`                                                                                                                                                                        | `yrt/exceptions.py`                                       |
| `config.py`: `_validate_config()` (batch 1–50, retries ≥ 0, timeout > 0, budgets > 0, thresholds > 0); new keys `api.daily_quota`, `jobs.daily.budget`, `jobs.updates.budget`, `lives.*`, `schedule.*` with defaults                    | `yrt/config.py`, `_config/constants.json`, CLAUDE.md      |
| **Bug:** `isodate.parse_duration(...).seconds` drops days for ≥ 24 h videos → `utils.parse_iso8601_duration()` using `total_seconds()`; un-skip the 3 duration tests                                                                    | `yrt/youtube/{utils,stats}.py`, `_tests/test_youtube.py`  |
| Error fixtures (`error_quota_exceeded.json`, `error_404_response.json`, `error_403_response.json`, `empty_playlist_response.json`) — IMPROVEMENTS #19                                                                                   | `_tests/fixtures/`                                        |
| Tests: retry paths (transient → retried, permanent → skipped, quota → `api_failure.json` + `QuotaExhaustedError`), tracker arithmetic, config validation                                                                                | `_tests/test_retry.py`, `test_quota.py`, `test_config.py` |

Acceptance: no behaviour change in the daily job; `history.log` gains one `Quota spent: N units` line per run.

### Phase 2 — Execution context & entry-point split (M) · `feat/execution-context`

Covers IMPROVEMENTS-2026 **#10, #13** (partially), **#11**.

| Task                                                                                                                                                                                                                                              | Files                                  |
|---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|----------------------------------------|
| `yrt/context.py`: `ExecutionContext(now, last_exe, job_name, last_exe_path, history_path)`; `utils.NOW` / `LAST_EXE` become aliases of a default context; `get_playlist_items` / `iter_channels` / `weekly_stats` / cleanup take `ctx` explicitly | `yrt/context.py`, `yrt/youtube/*`      |
| `yrt/runtime.py`: `bootstrap(exe_mode, job)` (service creation, prog-bar flag, loggers), `finalize(ctx, creds_b64)` (secret refresh, `copy_last_exe_log` **per job file**) — extracted from `main.py`                                             | `yrt/runtime.py`, `yrt/main.py`        |
| `main.py` reduced to `load_config()` + `run_daily(ctx, service)`; implement the config-loading (3), `copy_last_exe_log` (2) and exception-handling (2) tests from the skipped list                                                                | `yrt/main.py`, `_tests/test_main.py`   |
| Remove `yrt/analytics.py` (keep `_sandbox.py` ignored)                                                                                                                                                                                            | `yrt/`                                 |
| `paths.py`: `UPDATES_LAST_EXE_LOG`, `UPDATES_HISTORY_LOG`, `SCHEDULE_JSON`, `LIVES_STATE` if needed; `ALLOWED_DIRS` unchanged                                                                                                                     | `yrt/paths.py`, `_tests/test_paths.py` |

Acceptance: daily job byte-identical in behaviour; `test_main.py` skips drop from 20 to ≤ 13.

### Phase 3 — Lives detection & playlist update (L) · `feat/lives`

| Task                                                                                                                                              | Files                               |
|---------------------------------------------------------------------------------------------------------------------------------------------------|-------------------------------------|
| `LiveStream` model; `LIVE_TAB_PLAYLIST_PREFIX`; `LIVE_STATUS_*` reuse                                                                             | `yrt/models.py`, `yrt/constants.py` |
| `lives.py`: `get_live_candidates`, `find_live_streams`, `update_lives_playlist` (D1 policy, D2 cap, duplicate-safe insert at rank)                | `yrt/youtube/lives.py`              |
| `music_lives` gets `"cleanup_on_end": true` so the daily job's `cleanup_ended_streams` also covers it (belt and braces with the frequent job)     | `_config/playlists.json`            |
| `yrt/updates.py`: entry point `python -m yrt.updates {local\|action}` running **lives only** at this phase (mixes come in Phase 5)                | new                                 |
| `updates_workflow.yml` with a fixed `0 */2 * * *` cron for now (gate arrives in Phase 6), `run`-branch checkout, rebase-retry push, failure→issue | `.github/workflows/`                |
| Merge sister `toPass` (5 channels) after checking why they were skipped                                                                           | `_config/add-on.json`               |
| First-run catch-up: run once from **local mode** so the initial ~50–70 inserts (2,500–3,500 units) don't collide with the daily job's budget      | operator step, documented in README |
| Tests: candidates (incl. 404 → `[]`), status filtering, cap, duplicate prevention, removal policy, position insert                                | `_tests/test_lives.py`              |

Acceptance: playlist contains every current live from MUSIQUE ∪ certified (spot-check Lofi Girl: 22+ entries); frequent
job ≤ 400 units/run in `updates_history.log`.

### Phase 4 — Sorting (M) · `feat/lives-sorting`

| Task                                                                                                                              | Files                  |
|-----------------------------------------------------------------------------------------------------------------------------------|------------------------|
| `sort_lives_playlist()` per §4.5 (LIS, drift threshold, move cap, quota-guarded updates)                                          | `yrt/youtube/lives.py` |
| `sort` flag plumbed from CLI (`--sort`) until the gate provides it                                                                | `yrt/updates.py`       |
| Tests with the measured 33-item sample (expect 12 minimal moves → 6 after threshold), empty playlist, single item, already sorted | `_tests/test_lives.py` |

Acceptance: a sort pass costs ≤ 500 units; two passes/day ≤ 1,000.

### Phase 5 — Mixes (M) · `feat/mixes`

| Task                                                                                                                                                                                                  | Files                                         |
|-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|-----------------------------------------------|
| `RouterConfig.mixes_id`; `_route_music` long + music-only → `mixes`; `certified` folded into music channels for routing; router tests updated (expect 4–6 new cases)                                  | `yrt/router.py`, `_tests/test_router.py`      |
| `mixes.retention_days = 7`                                                                                                                                                                            | `_config/playlists.json`                      |
| `updates.py` gains the mixes pass: `iter_channels(MUSIQUE ∪ certified − toPass, ctx=updates_ctx)` → `add_stats` → route → add only `mixes` destinations (everything else is the daily job's business) | `yrt/updates.py`                              |
| Optional `feeds.py` RSS pre-filter (D4/§4.6); full pass on the day's first slot                                                                                                                       | `yrt/youtube/feeds.py`                        |
| Archive `mix_history.csv` (D8); `archive_data.py` learns the `updates_history.log` file — and swap its broad `except Exception` for the specific yrt exceptions (IMPROVEMENTS #15) while touching it  | `_archive/_data/`, `_scripts/archive_data.py` |

Acceptance: mixes added within one slot of release, removed after 7 days; `stats.csv` unchanged in shape.

### Phase 6 — Adaptive schedule (M) · `feat/adaptive-schedule`

| Task                                                                                                                                                                                    | Files                                                           |
|-----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|-----------------------------------------------------------------|
| `_scripts/adjust_schedule.py` (port of `cron_update.py` onto `stats.csv`, writes `_data/schedule.json`); pure pandas, `YRT_NO_LOGGING=1`, function-level imports like the other scripts | `_scripts/adjust_schedule.py`, `_tests/test_adjust_schedule.py` |
| `yrt/schedule_gate.py` (`run=`, `sort=` outputs; 90-min gate window; weekday in UTC)                                                                                                    | new, `_tests/test_schedule_gate.py`                             |
| `main_workflow.yml`: step `uv run python _scripts/adjust_schedule.py` before commit                                                                                                     | `.github/workflows/`                                            |
| `updates_workflow.yml`: hourly cron, gate step, `if: steps.gate.outputs.run == 'true'` on the job steps                                                                                 | `.github/workflows/`                                            |
| Seed `_data/schedule.json` on `run` from the sister's current cron table                                                                                                                | operator step                                                   |

Acceptance: gate decisions visible in the Actions summary; no workflow file changes after seeding.

### Phase 7 — Retire & document (S) · `feat/port-docs`

| Task                                                                                                                                                      | Where                        |
|-----------------------------------------------------------------------------------------------------------------------------------------------------------|------------------------------|
| Disable the sister's `Playlists updates` and `Adjust updates schedule` schedules (keep `workflow_dispatch`); archive the repository after two clean weeks | sister repo                  |
| CLAUDE.md: new modules, two-job model, state split, quota guard, schedule data; README: playlists list, operator steps                                    | this repo                    |
| Mark IMPROVEMENTS-2026 items #8 #9 #10 #11 #14 #15 #17 #19 as done, with PR numbers                                                                       | `_docs/IMPROVEMENTS-2026.md` |

---

## 6. Quota budget after the port

| Line item                                          | Units/run                       | Runs/day      | Units/day                                                 |
|----------------------------------------------------|---------------------------------|---------------|-----------------------------------------------------------|
| Daily job (unchanged)                              | 1,000–4,000                     | 1             | 1,000–4,000                                               |
| Lives detection (UULV + `videos.list`)             | ~200–370                        | ~6 (adaptive) | 1,200–2,200                                               |
| Lives detection with `/live` pre-filter (optional) | ~15–30                          | ~6            | ~100–200                                                  |
| Lives add/remove (~2–4 events/day)                 | —                               | —             | 100–200                                                   |
| Lives sorting (D5)                                 | ≤ 500                           | 2             | ≤ 1,000                                                   |
| Mixes discovery in the frequent job                | 184 (→ ~10 with RSS pre-filter) | ~6            | 1,100 (→ ~60)                                             |
| Mixes add (5/day avg, 13 peak)                     | —                               | —             | 250–650                                                   |
| Mixes retention (deletes)                          | —                               | —             | 250–650                                                   |
| Adaptive schedule + gate                           | 0                               | —             | 0                                                         |
| **Total**                                          |                                 |               | **≈ 4,000–9,000 without pre-filters, ≈ 3,000–7,000 with** |

Budgets (D6): daily job 7,000, frequent job 2,500 aggregated — the guard drops sorting first. If the guard trips more
than a few times a month, file the quota-extension form before considering a second project.

One-off: first catch-up run ≈ 2,500–3,500 units (Phase 3, run locally).

---

## 7. Risks

| Risk                                                                           | Mitigation                                                                                                                     |
|--------------------------------------------------------------------------------|--------------------------------------------------------------------------------------------------------------------------------|
| `UULV…` playlist IDs are undocumented and could disappear                      | `LiveSource` abstraction; fallback to the `/live` canonical probe; alert (issue) when > 50 % of channels return 404 in one run |
| HTML served to datacenter IPs differs from residential (what broke the sister) | HTML probes are optional pre-filters only; the API path never depends on them                                                  |
| Duplicate playlist entries (YouTube allows them)                               | always diff against current playlist items before insert                                                                       |
| Two workflows committing to `run`                                              | separate log/last-exe files; rebase-retry push; `concurrency:` group on the frequent workflow                                  |
| Viewer-count jitter makes sorting expensive                                    | drift threshold + move cap + ≤ 2 sort slots                                                                                    |
| Playlist grows to 80–100 lives                                                 | D2 knob `lives.max_per_channel`; playlist limit is 5,000 so no hard wall                                                       |
| GitHub scheduler lag (IMPROVEMENTS #20)                                        | gate window instead of exact-hour match; idempotent job so a double run is harmless                                            |
| Token refresh race between jobs                                                | refresh token is stable; last secret writer wins; both jobs refresh on 401                                                     |
| Quota exhaustion mid-run                                                       | guard ordering adds → removals → sorting; adds spill to `api_failure.json` (existing)                                          |

---

## 8. Effort

| Phase                       | Size                      | Notes                                      |
|-----------------------------|---------------------------|--------------------------------------------|
| 0 Hotfix + doc hygiene      | S                         | unblocks Mixes today                       |
| 1 Foundations               | L                         | replaces the separate "quota tracker" item |
| 2 Execution context & split | M                         | prerequisite for a second job              |
| 3 Lives                     | L                         | includes workflow + first catch-up         |
| 4 Sorting                   | M                         |                                            |
| 5 Mixes                     | M                         | includes RSS pre-filter if wanted          |
| 6 Adaptive schedule         | M                         |                                            |
| 7 Retire & document         | S                         |                                            |
| **Total**                   | **≈ 7–9 dev-days, 8 PRs** | ship to `main` after 3 and after 6         |

Monetary cost: none (API free tier, Actions free on a public repo; the hourly gate run is ~30 s).

---

## 9. IMPROVEMENTS-2026 items deliberately left out

#7 pathlib consistency, #16 service context manager, #18 TypedDict/Protocol — none touch the port's surface; keep them
in the 2026 backlog. #20 is already accepted and only informs the gate design.

---

## 10. Open questions for the operator

1. Confirm D1 (live + upcoming) — it changes what the daily router keeps doing with music premieres/streams.
2. Confirm D4 (mixes in the frequent job) — the alternative makes Phase 6 unnecessary.
3. Why were the 5 sister `toPass` channels skipped? Bad upload playlists or preference? (Phase 3.)
4. Should the frequent job's `updates_history.log` be committed at all, or is the Actions log enough? (Phase 2.)