"""Zero-quota smoke test: the daily job's orchestration functions flow through the retry/quota layer together.

This is the offline stand-in for "does the daily job still run": the real functions are driven against the mock
client with fixture-shaped responses and a temp api_failure.json, and the exact quota total is asserted.
"""

# Standard library
import datetime as dt
import json
from types import SimpleNamespace

# Third-party
import pytest

# Local
from yrt.constants import QUOTA_COST_LIST, QUOTA_COST_WRITE
from yrt.models import PlaylistConfig
from yrt.youtube import quota, utils
from yrt.youtube.api import iter_channels
from yrt.youtube.cleanup import cleanup_expired_videos
from yrt.youtube.playlist import add_api_fail, add_to_playlist

RELEASE_RADAR = 'PLrelease0000000000000000000000000'
CATEGORY_PLAYLIST = 'PLcategory000000000000000000000000'
CHANNELS = {'ok': 'UCok000000000000000000', 'gone': 'UCgone00000000000000000', 'flaky': 'UCflaky0000000000000000'}


def _upload(video_id, channel_id):
    """Build an upload-playlist item inside the pinned window."""
    return SimpleNamespace(
        id=f'item_{video_id}',
        contentDetails=SimpleNamespace(videoId=video_id, videoPublishedAt='2024-01-15T12:00:00Z'),
        snippet=SimpleNamespace(title=video_id, videoOwnerChannelId=channel_id, videoOwnerChannelTitle=channel_id),
        status=SimpleNamespace(privacyStatus='public'),
    )


def _page(items):
    """Build a single-page playlistItems.list response."""
    return SimpleNamespace(items=items, nextPageToken=None)


@pytest.fixture
def daily_job_state(tmp_path, monkeypatch):
    """Pin the date window, the add-on lists and a temp api_failure.json with one saved failure."""
    from yrt import paths

    monkeypatch.setattr(utils, 'LAST_EXE', dt.datetime(2024, 1, 1, tzinfo=dt.UTC))
    monkeypatch.setattr(utils, 'ADD_ON', {'playlistNotFoundPass': [], 'toPass': []})

    api_failure = tmp_path / 'api_failure.json'
    api_failure.write_text(
        json.dumps({RELEASE_RADAR: {'name': 'Release Radar', 'description': '', 'failure': ['saved00001']}}),
        encoding='utf-8',
    )
    monkeypatch.setattr(paths, 'API_FAILURE_JSON', api_failure)
    return api_failure


@pytest.mark.integration
class TestDailyFlowSmoke:
    """Drive the daily job's steps in order and account for every quota unit."""

    @staticmethod
    def test_daily_flow_accounts_every_unit(mock_youtube_client, quota_tracker, api_error, no_sleep, daily_job_state):
        """Test replay -> discovery (ok / 404 / 503-then-ok) -> quota-limited adds -> retention cleanup."""
        flaky_calls = {'count': 0}

        def playlist_items_list(**kwargs):
            """Answer per playlist: the three upload playlists, then the category playlist for cleanup."""
            playlist_id = kwargs['playlist_id']
            if playlist_id == f'UU{CHANNELS["ok"][2:]}':
                return _page([_upload('okvideo001', CHANNELS['ok'])])
            if playlist_id == f'UU{CHANNELS["gone"][2:]}':
                raise api_error('error_404_response.json')
            if playlist_id == f'UU{CHANNELS["flaky"][2:]}':
                flaky_calls['count'] += 1
                if flaky_calls['count'] == 1:
                    raise api_error('error_503_backend.json')
                return _page([_upload('flakyvid01', CHANNELS['flaky'])])
            if playlist_id == CATEGORY_PLAYLIST:
                expired = SimpleNamespace(
                    id='item_expired01',
                    contentDetails=SimpleNamespace(videoId='expired001'),
                    snippet=SimpleNamespace(publishedAt='2020-01-01T00:00:00Z'),
                )
                return _page([expired])
            raise AssertionError(f'unexpected playlist {playlist_id}')

        mock_youtube_client.playlistItems.list.side_effect = playlist_items_list
        # First insert (the replayed failure) succeeds, the two new videos hit the quota wall
        mock_youtube_client.playlistItems.insert.side_effect = [
            None,
            api_error('error_quota_exceeded.json'),
            api_error('error_quota_exceeded.json'),
        ]

        # 1. Replay yesterday's failure: 1 insert = 50 units
        add_api_fail(mock_youtube_client, prog_bar=False)

        # 2. Discover uploads: ok (1) + gone 404 (1) + flaky 503 then ok (2) = 4 units
        new_videos = iter_channels(
            mock_youtube_client,
            list(CHANNELS.values()),
            latest_d=dt.datetime(2024, 2, 1, tzinfo=dt.UTC),
            prog_bar=False,
        )
        assert sorted(video.video_id for video in new_videos) == ['flakyvid01', 'okvideo001']

        # 3. Add them: both rejected for quota = 0 units, both saved for tomorrow
        add_to_playlist(mock_youtube_client, RELEASE_RADAR, ['okvideo001', 'flakyvid01'], prog_bar=False)

        # 4. Retention cleanup: 1 list (1) + 1 delete (50) = 51 units
        playlists = {'cat': PlaylistConfig(id=CATEGORY_PLAYLIST, name='Category', description='', retention_days=7)}
        cleanup_expired_videos(mock_youtube_client, playlists, prog_bar=False)

        expected = QUOTA_COST_WRITE + 4 * QUOTA_COST_LIST + QUOTA_COST_LIST + QUOTA_COST_WRITE
        assert quota_tracker.spent == expected
        assert quota.get_tracker().summary().startswith(f'Quota spent: {expected} units')
        assert no_sleep.call_count == 1  # the single 503 retry

        saved = json.loads(daily_job_state.read_text(encoding='utf-8'))[RELEASE_RADAR]['failure']
        assert saved == ['okvideo001', 'flakyvid01']  # replayed one cleared, new ones queued
        assert mock_youtube_client.playlistItems.delete.call_args.kwargs['playlist_item_id'] == 'item_expired01'
