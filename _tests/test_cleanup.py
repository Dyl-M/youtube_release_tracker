"""Tests for yrt/youtube/cleanup.py - Retention and ended-stream cleanup through the retry layer."""

# Standard library
from types import SimpleNamespace

# Third-party
import pytest

# Local
from yrt.constants import QUOTA_COST_LIST, QUOTA_COST_WRITE
from yrt.models import PlaylistConfig
from yrt.youtube.cleanup import cleanup_ended_streams, cleanup_expired_videos

PLAYLIST_ID = 'PLcleanup000000000000000000000000'
EXPIRED_AT = '2020-01-01T00:00:00Z'
FRESH_AT = '2999-01-01T00:00:00Z'


def _item(video_id, added_at=FRESH_AT):
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


def _deleted_item_ids(mock_youtube_client):
    """Return the playlist item IDs passed to playlistItems.delete, in call order."""
    return [call.kwargs['playlist_item_id'] for call in mock_youtube_client.playlistItems.delete.call_args_list]


@pytest.fixture
def retention_playlists():
    """One playlist with a 7-day retention and one without any cleanup rule."""
    return {
        'kept': PlaylistConfig(id='PLkept', name='Kept', description=''),
        'pruned': PlaylistConfig(id=PLAYLIST_ID, name='Pruned', description='', retention_days=7),
    }


@pytest.fixture
def stream_playlists():
    """One playlist with cleanup_on_end and one without."""
    return {
        'streams': PlaylistConfig(id=PLAYLIST_ID, name='Streams', description='', cleanup_on_end=True),
        'other': PlaylistConfig(id='PLother', name='Other', description=''),
    }


@pytest.mark.unit
@pytest.mark.api
class TestCleanupExpiredVideos:
    """Test retention cleanup: expiry filtering and the partial-results behaviour on errors."""

    @staticmethod
    def test_deletes_expired_items_only(mock_youtube_client, quota_tracker, retention_playlists):
        """Test only items added before the cutoff are deleted, and playlists without retention are skipped."""
        mock_youtube_client.playlistItems.list.return_value = _page(
            [_item('old0000001', EXPIRED_AT), _item('new0000001', FRESH_AT)]
        )

        cleanup_expired_videos(mock_youtube_client, retention_playlists, prog_bar=False)

        assert mock_youtube_client.playlistItems.list.call_count == 1
        assert _deleted_item_ids(mock_youtube_client) == ['item_old0000001']
        assert quota_tracker.spent == QUOTA_COST_LIST + QUOTA_COST_WRITE

    @staticmethod
    def test_paginates_and_deletes_across_pages(mock_youtube_client, quota_tracker, retention_playlists):
        """Test expired items from every page are deleted."""
        mock_youtube_client.playlistItems.list.side_effect = [
            _page([_item('old0000001', EXPIRED_AT)], next_page='page2'),
            _page([_item('old0000002', EXPIRED_AT), _item('new0000001', FRESH_AT)]),
        ]

        cleanup_expired_videos(mock_youtube_client, retention_playlists, prog_bar=False)

        assert _deleted_item_ids(mock_youtube_client) == ['item_old0000001', 'item_old0000002']
        assert quota_tracker.spent == 2 * QUOTA_COST_LIST + 2 * QUOTA_COST_WRITE

    @staticmethod
    def test_quota_error_on_second_page_keeps_first_page(
        mock_youtube_client, quota_tracker, retention_playlists, api_error, history_mock
    ):
        """Test a quota rejection mid-pagination still deletes what was gathered and logs the quota warning."""
        mock_youtube_client.playlistItems.list.side_effect = [
            _page([_item('old0000001', EXPIRED_AT)], next_page='page2'),
            api_error('error_quota_exceeded.json'),
        ]

        cleanup_expired_videos(mock_youtube_client, retention_playlists, prog_bar=False)

        assert _deleted_item_ids(mock_youtube_client) == ['item_old0000001']
        message, *args = history_mock.warning.call_args.args
        assert message % tuple(args) == 'API quota exceeded while checking retention for Pruned'

    @staticmethod
    def test_other_error_is_logged_and_nothing_is_deleted(
        mock_youtube_client, quota_tracker, retention_playlists, api_error, no_sleep, history_mock
    ):
        """Test a non-quota failure on the listing deletes nothing and logs the generic warning."""
        mock_youtube_client.playlistItems.list.side_effect = api_error('error_404_response.json')

        cleanup_expired_videos(mock_youtube_client, retention_playlists, prog_bar=False)

        assert mock_youtube_client.playlistItems.delete.call_count == 0
        assert 'Error fetching items from' in history_mock.warning.call_args.args[0]


@pytest.mark.unit
@pytest.mark.api
class TestCleanupEndedStreams:
    """Test ended-stream cleanup: status filtering, pagination and error handling."""

    @staticmethod
    def test_deletes_ended_streams_only(mock_youtube_client, quota_tracker, stream_playlists):
        """Test only videos whose liveBroadcastContent is 'none' are deleted; live and upcoming stay."""
        mock_youtube_client.playlistItems.list.return_value = _page(
            [_item('done000001'), _item('live000001'), _item('soon000001')]
        )
        mock_youtube_client.videos.list.return_value = SimpleNamespace(
            items=[_video('done000001', 'none'), _video('live000001', 'live'), _video('soon000001', 'upcoming')]
        )

        cleanup_ended_streams(mock_youtube_client, stream_playlists, prog_bar=False)

        assert _deleted_item_ids(mock_youtube_client) == ['item_done000001']
        assert quota_tracker.spent == 2 * QUOTA_COST_LIST + QUOTA_COST_WRITE

    @staticmethod
    def test_paginates_before_checking_statuses(mock_youtube_client, quota_tracker, stream_playlists):
        """Test items from every page are status-checked and ended ones deleted."""
        mock_youtube_client.playlistItems.list.side_effect = [
            _page([_item('done000001')], next_page='page2'),
            _page([_item('done000002')]),
        ]
        mock_youtube_client.videos.list.return_value = SimpleNamespace(
            items=[_video('done000001', 'none'), _video('done000002', 'none')]
        )

        cleanup_ended_streams(mock_youtube_client, stream_playlists, prog_bar=False)

        assert _deleted_item_ids(mock_youtube_client) == ['item_done000001', 'item_done000002']
        assert quota_tracker.spent == 3 * QUOTA_COST_LIST + 2 * QUOTA_COST_WRITE

    @staticmethod
    def test_status_check_error_deletes_nothing(
        mock_youtube_client, quota_tracker, stream_playlists, api_error, no_sleep, history_mock
    ):
        """Test a failing videos.list logs a warning and no stream is removed."""
        mock_youtube_client.playlistItems.list.return_value = _page([_item('done000001')])
        mock_youtube_client.videos.list.side_effect = api_error('error_503_backend.json')

        cleanup_ended_streams(mock_youtube_client, stream_playlists, prog_bar=False)

        assert mock_youtube_client.playlistItems.delete.call_count == 0
        assert 'Error checking stream status' in history_mock.warning.call_args.args[0]

    @staticmethod
    def test_listing_error_logs_streams_warning(
        mock_youtube_client, quota_tracker, stream_playlists, api_error, history_mock
    ):
        """Test a quota rejection while listing the stream playlist logs the streams-specific warning."""
        mock_youtube_client.playlistItems.list.side_effect = api_error('error_quota_exceeded.json')

        cleanup_ended_streams(mock_youtube_client, stream_playlists, prog_bar=False)

        assert mock_youtube_client.videos.list.call_count == 0
        message, *args = history_mock.warning.call_args.args
        assert message % tuple(args) == 'API quota exceeded while checking streams for Streams'

    @staticmethod
    def test_empty_playlist_makes_no_status_call(mock_youtube_client, quota_tracker, stream_playlists):
        """Test an empty stream playlist skips the videos.list check entirely."""
        mock_youtube_client.playlistItems.list.return_value = _page([])

        cleanup_ended_streams(mock_youtube_client, stream_playlists, prog_bar=False)

        assert mock_youtube_client.videos.list.call_count == 0
        assert quota_tracker.spent == QUOTA_COST_LIST
