"""Tests for yrt/youtube/cleanup.py - Retention and ended-stream cleanup through the retry layer."""

# Standard library
import datetime as dt
from types import SimpleNamespace

# Third-party
import pytest

# Local
from yrt.constants import QUOTA_COST_LIST, QUOTA_COST_WRITE
from yrt.models import PlaylistConfig, PlaylistItemRef
from yrt.youtube.cleanup import (
    _fetch_expired_items,
    _fetch_stream_playlist_items,
    _find_ended_streams,
    cleanup_ended_streams,
    cleanup_expired_videos,
)

PLAYLIST_ID = 'PLcleanup000000000000000000000000'
CUTOFF = dt.datetime(2024, 1, 10, tzinfo=dt.UTC)


def _item(video_id, added_at='2024-01-15T12:00:00Z'):
    """Build a playlist item with the fields cleanup reads."""
    return SimpleNamespace(
        id=f'item_{video_id}',
        contentDetails=SimpleNamespace(videoId=video_id),
        snippet=SimpleNamespace(publishedAt=added_at),
    )


def _page(items, next_page=None):
    """Build one playlistItems.list response page."""
    return SimpleNamespace(items=items, nextPageToken=next_page)


def _video(video_id, live_status):
    """Build a videos.list item with the live status."""
    return SimpleNamespace(id=video_id, snippet=SimpleNamespace(liveBroadcastContent=live_status))


@pytest.mark.unit
@pytest.mark.api
class TestFetchExpiredItems:
    """Test _fetch_expired_items() filtering and its partial-results behaviour on errors."""

    @staticmethod
    def test_returns_items_added_before_cutoff(mock_youtube_client, quota_tracker):
        """Test only items added before the cutoff are returned, with their add date."""
        mock_youtube_client.playlistItems.list.return_value = _page(
            [_item('old0000001', '2024-01-01T00:00:00Z'), _item('new0000001', '2024-01-15T00:00:00Z')]
        )

        expired = _fetch_expired_items(mock_youtube_client, PLAYLIST_ID, 'Test', CUTOFF)

        assert [item.video_id for item in expired] == ['old0000001']
        assert expired[0].add_date == dt.datetime(2024, 1, 1, tzinfo=dt.UTC)
        assert quota_tracker.spent == QUOTA_COST_LIST

    @staticmethod
    def test_quota_error_on_second_page_keeps_first_page(mock_youtube_client, quota_tracker, api_error, history_mock):
        """Test a quota rejection mid-pagination returns what was gathered and logs the quota warning."""
        mock_youtube_client.playlistItems.list.side_effect = [
            _page([_item('old0000001', '2024-01-01T00:00:00Z')], next_page='page2'),
            api_error('error_quota_exceeded.json'),
        ]

        expired = _fetch_expired_items(mock_youtube_client, PLAYLIST_ID, 'Test', CUTOFF)

        assert [item.video_id for item in expired] == ['old0000001']
        message, *args = history_mock.warning.call_args.args
        assert message % tuple(args) == 'API quota exceeded while checking retention for Test'

    @staticmethod
    def test_other_error_is_logged_generically(mock_youtube_client, quota_tracker, api_error, no_sleep, history_mock):
        """Test a non-quota failure returns an empty list with the generic warning."""
        mock_youtube_client.playlistItems.list.side_effect = api_error('error_404_response.json')

        assert _fetch_expired_items(mock_youtube_client, PLAYLIST_ID, 'Test', CUTOFF) == []
        assert 'Error fetching items from' in history_mock.warning.call_args.args[0]


@pytest.mark.unit
@pytest.mark.api
class TestStreamPlaylist:
    """Test the ended-stream detection helpers."""

    @staticmethod
    def test_fetch_stream_items_paginates(mock_youtube_client, quota_tracker):
        """Test all pages are gathered into PlaylistItemRef instances."""
        mock_youtube_client.playlistItems.list.side_effect = [
            _page([_item('vid0000001')], next_page='page2'),
            _page([_item('vid0000002')]),
        ]

        items = _fetch_stream_playlist_items(mock_youtube_client, PLAYLIST_ID, 'Streams')

        assert [item.video_id for item in items] == ['vid0000001', 'vid0000002']
        assert quota_tracker.spent == 2 * QUOTA_COST_LIST

    @staticmethod
    def test_find_ended_streams_keeps_only_none_status(mock_youtube_client, quota_tracker):
        """Test videos whose liveBroadcastContent is 'none' are reported as ended."""
        mock_youtube_client.videos.list.return_value = SimpleNamespace(
            items=[_video('done000001', 'none'), _video('live000001', 'live'), _video('soon000001', 'upcoming')]
        )
        refs = [
            PlaylistItemRef(item_id='i1', video_id='done000001'),
            PlaylistItemRef(item_id='i2', video_id='live000001'),
            PlaylistItemRef(item_id='i3', video_id='soon000001'),
        ]

        ended = _find_ended_streams(mock_youtube_client, refs)

        assert [item.video_id for item in ended] == ['done000001']

    @staticmethod
    def test_find_ended_streams_error_is_logged(mock_youtube_client, quota_tracker, api_error, no_sleep, history_mock):
        """Test a failing status check logs a warning and reports nothing as ended."""
        mock_youtube_client.videos.list.side_effect = api_error('error_503_backend.json')

        ended = _find_ended_streams(mock_youtube_client, [PlaylistItemRef(item_id='i1', video_id='done000001')])

        assert ended == []
        assert 'Error checking stream status' in history_mock.warning.call_args.args[0]


@pytest.mark.unit
@pytest.mark.api
class TestCleanupOrchestration:
    """Test the two public cleanup entry points end to end against the mock client."""

    @staticmethod
    def test_cleanup_expired_videos_deletes_expired_only(mock_youtube_client, quota_tracker):
        """Test playlists with retention_days get their expired items deleted; others are skipped."""
        mock_youtube_client.playlistItems.list.return_value = _page(
            [_item('old0000001', '2020-01-01T00:00:00Z'), _item('new0000001', '2999-01-01T00:00:00Z')]
        )
        playlists = {
            'kept': PlaylistConfig(id='PLkept', name='Kept', description=''),
            'pruned': PlaylistConfig(id=PLAYLIST_ID, name='Pruned', description='', retention_days=7),
        }

        cleanup_expired_videos(mock_youtube_client, playlists, prog_bar=False)

        assert mock_youtube_client.playlistItems.list.call_count == 1
        assert mock_youtube_client.playlistItems.delete.call_count == 1
        assert mock_youtube_client.playlistItems.delete.call_args.kwargs['playlist_item_id'] == 'item_old0000001'
        assert quota_tracker.spent == QUOTA_COST_LIST + QUOTA_COST_WRITE

    @staticmethod
    def test_cleanup_ended_streams_deletes_ended_only(mock_youtube_client, quota_tracker):
        """Test playlists with cleanup_on_end get their ended streams deleted."""
        mock_youtube_client.playlistItems.list.return_value = _page([_item('done000001'), _item('live000001')])
        mock_youtube_client.videos.list.return_value = SimpleNamespace(
            items=[_video('done000001', 'none'), _video('live000001', 'live')]
        )
        playlists = {
            'streams': PlaylistConfig(id=PLAYLIST_ID, name='Streams', description='', cleanup_on_end=True),
            'other': PlaylistConfig(id='PLother', name='Other', description=''),
        }

        cleanup_ended_streams(mock_youtube_client, playlists, prog_bar=False)

        assert mock_youtube_client.playlistItems.delete.call_count == 1
        assert mock_youtube_client.playlistItems.delete.call_args.kwargs['playlist_item_id'] == 'item_done000001'
        assert quota_tracker.spent == 2 * QUOTA_COST_LIST + QUOTA_COST_WRITE

    @staticmethod
    def test_cleanup_ended_streams_with_empty_playlist_makes_no_status_call(mock_youtube_client, quota_tracker):
        """Test an empty stream playlist skips the videos.list check entirely."""
        mock_youtube_client.playlistItems.list.return_value = _page([])
        playlists = {'streams': PlaylistConfig(id=PLAYLIST_ID, name='Streams', description='', cleanup_on_end=True)}

        cleanup_ended_streams(mock_youtube_client, playlists, prog_bar=False)

        assert mock_youtube_client.videos.list.call_count == 0
        assert quota_tracker.spent == QUOTA_COST_LIST
