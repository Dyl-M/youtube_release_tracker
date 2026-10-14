"""Tests for yrt/youtube/api.py - Core API calls through the retry layer."""

# Standard library
from types import SimpleNamespace

# Third-party
import pytest

# Local
from yrt.constants import QUOTA_COST_LIST
from yrt.exceptions import APIError, ErrorCategory
from yrt.models import AddOnConfig
from yrt.youtube.api import check_if_live, get_playlist_items, get_subs, get_videos, iter_channels

CHANNEL_ID = 'UCchannel00000000000000'
PLAYLIST_ID = 'UUchannel00000000000000'


def _item(video_id, published_at: str | None = '2024-01-15T12:00:00Z', status='public'):
    """Build a playlist item shaped like the client's response objects."""
    return SimpleNamespace(
        id=f'item_{video_id}',
        contentDetails=SimpleNamespace(videoId=video_id, videoPublishedAt=published_at),
        snippet=SimpleNamespace(
            title=f'Title {video_id}', videoOwnerChannelId=CHANNEL_ID, videoOwnerChannelTitle='Channel'
        ),
        status=SimpleNamespace(privacyStatus=status),
    )


def _page(items, next_page_token=None):
    """Build one playlistItems.list response page."""
    return SimpleNamespace(items=items, nextPageToken=next_page_token)


def _video(video_id, live_status='none'):
    """Build a videos.list item with just what check_if_live reads."""
    return SimpleNamespace(id=video_id, snippet=SimpleNamespace(liveBroadcastContent=live_status))


@pytest.mark.unit
@pytest.mark.api
class TestGetPlaylistItems:
    """Test get_playlist_items() parsing, filtering and error handling (window: January 2024, from exec_context)."""

    @staticmethod
    def test_returns_items_inside_the_window(mock_youtube_client, quota_tracker, exec_context):
        """Test items released between ctx.last_exe and ctx.now are returned, older ones dropped."""
        mock_youtube_client.playlistItems.list.return_value = _page(
            [_item('inside001'), _item('older0001', published_at='2023-12-01T12:00:00Z')]
        )

        items = get_playlist_items(mock_youtube_client, PLAYLIST_ID, CHANNEL_ID, exec_context)

        assert [item.video_id for item in items] == ['inside001']
        assert items[0].source_channel_id == CHANNEL_ID
        assert quota_tracker.spent == QUOTA_COST_LIST

    @staticmethod
    def test_scheduled_items_without_publish_date_are_dropped(mock_youtube_client, quota_tracker, exec_context):
        """Test premieres/scheduled videos (videoPublishedAt None) are skipped until they go live."""
        mock_youtube_client.playlistItems.list.return_value = _page(
            [_item('sched0001', published_at=None), _item('inside001')]
        )

        items = get_playlist_items(mock_youtube_client, PLAYLIST_ID, CHANNEL_ID, exec_context)

        assert [item.video_id for item in items] == ['inside001']

    @staticmethod
    def test_day_ago_replaces_the_lower_bound(mock_youtube_client, quota_tracker, exec_context):
        """Test day_ago= keeps only the items released within that many days before ctx.now."""
        mock_youtube_client.playlistItems.list.return_value = _page(
            [_item('recent001', published_at='2024-01-31T12:00:00Z'), _item('inside001')]
        )

        items = get_playlist_items(mock_youtube_client, PLAYLIST_ID, CHANNEL_ID, exec_context, day_ago=2)

        assert [item.video_id for item in items] == ['recent001']

    @staticmethod
    def test_playlist_not_found_returns_empty_with_warning(
        mock_youtube_client, quota_tracker, exec_context, api_error, history_mock
    ):
        """Test a 404 yields an empty list and one 'Playlist not found' warning."""
        mock_youtube_client.playlistItems.list.side_effect = api_error('error_404_response.json')

        items = get_playlist_items(mock_youtube_client, PLAYLIST_ID, CHANNEL_ID, exec_context)

        assert items == []
        assert history_mock.warning.call_count == 1
        assert 'Playlist not found' in history_mock.warning.call_args.args[0]
        assert quota_tracker.spent == QUOTA_COST_LIST  # a 404 still costs a unit

    @staticmethod
    def test_playlist_not_found_pass_is_silent(
        mock_youtube_client, quota_tracker, exec_context, api_error, history_mock
    ):
        """Test a 404 for a channel listed in not_found_pass is not logged."""
        mock_youtube_client.playlistItems.list.side_effect = api_error('error_404_response.json')

        items = get_playlist_items(
            mock_youtube_client, PLAYLIST_ID, CHANNEL_ID, exec_context, not_found_pass=[CHANNEL_ID]
        )

        assert items == []
        assert history_mock.warning.call_count == 0

    @staticmethod
    def test_other_errors_raise_api_error(mock_youtube_client, quota_tracker, exec_context, api_error, no_sleep):
        """Test a non-404 failure is re-raised as APIError with the playlist ID and status attached."""
        mock_youtube_client.playlistItems.list.side_effect = api_error('error_403_response.json')

        with pytest.raises(APIError, match=r'Unknown error') as exc_info:
            get_playlist_items(mock_youtube_client, PLAYLIST_ID, CHANNEL_ID, exec_context)

        assert PLAYLIST_ID in str(exc_info.value)
        assert exc_info.value.status_code == 403
        assert exc_info.value.category is ErrorCategory.PERMANENT

    @staticmethod
    def test_transient_error_is_retried(mock_youtube_client, quota_tracker, exec_context, api_error, no_sleep):
        """Test a transient failure on the list call is retried and the page is still returned."""
        mock_youtube_client.playlistItems.list.side_effect = [
            api_error('error_503_backend.json'),
            _page([_item('inside001')]),
        ]

        items = get_playlist_items(mock_youtube_client, PLAYLIST_ID, CHANNEL_ID, exec_context)

        assert [item.video_id for item in items] == ['inside001']
        assert mock_youtube_client.playlistItems.list.call_count == 2
        assert quota_tracker.spent == 2 * QUOTA_COST_LIST


@pytest.mark.unit
@pytest.mark.api
class TestIterChannels:
    """Test iter_channels() applies the add-on filters and gathers every channel's items."""

    @staticmethod
    def test_skips_to_pass_channels_and_whitelists_missing_playlists(
        mock_youtube_client, quota_tracker, exec_context, api_error, history_mock
    ):
        """Test to_pass channels are never listed and a playlist_not_found_pass channel fails silently."""
        skipped, gone = 'UCskipped00000000000000', 'UCgone00000000000000000'

        def playlist_items_list(**kwargs):
            """One item for the regular channel, a 404 for the whitelisted one."""
            if kwargs['playlist_id'] == PLAYLIST_ID:
                return _page([_item('inside001')])
            if kwargs['playlist_id'] == f'UU{gone[2:]}':
                raise api_error('error_404_response.json')
            raise AssertionError(f'unexpected playlist {kwargs["playlist_id"]}')

        mock_youtube_client.playlistItems.list.side_effect = playlist_items_list
        add_on = AddOnConfig(favorites={}, playlist_not_found_pass=[gone], to_pass=[skipped])

        items = iter_channels(mock_youtube_client, [CHANNEL_ID, skipped, gone], exec_context, add_on, prog_bar=False)

        assert [item.video_id for item in items] == ['inside001']
        assert mock_youtube_client.playlistItems.list.call_count == 2
        assert history_mock.warning.call_count == 0


@pytest.mark.unit
@pytest.mark.api
class TestGetVideos:
    """Test get_videos() and the functions built on it."""

    @staticmethod
    def test_returns_response_items(mock_youtube_client, quota_tracker):
        """Test get_videos() returns the response's items and charges one unit."""
        mock_youtube_client.videos.list.return_value = SimpleNamespace(items=[_video('vid0000001')])

        result = get_videos(mock_youtube_client, ['vid0000001'])

        assert [video.id for video in result] == ['vid0000001']
        assert quota_tracker.spent == QUOTA_COST_LIST

    @staticmethod
    def test_error_raises_api_error(mock_youtube_client, quota_tracker, api_error, no_sleep):
        """Test a failing videos.list raises APIError instead of the raw client exception."""
        mock_youtube_client.videos.list.side_effect = api_error('error_403_response.json')

        with pytest.raises(APIError) as exc_info:
            get_videos(mock_youtube_client, ['vid0000001'])

        assert exc_info.value.reason == 'forbidden'

    @staticmethod
    def test_check_if_live_maps_statuses(mock_youtube_client, quota_tracker):
        """Test check_if_live() returns video_id / live_status pairs."""
        mock_youtube_client.videos.list.return_value = SimpleNamespace(
            items=[_video('live000001', 'live'), _video('done000001', 'none')]
        )

        result = check_if_live(mock_youtube_client, ['live000001', 'done000001'])

        assert result == [
            {'video_id': 'live000001', 'live_status': 'live'},
            {'video_id': 'done000001', 'live_status': 'none'},
        ]

    @staticmethod
    def test_check_if_live_reraises_with_context(mock_youtube_client, quota_tracker, api_error, no_sleep):
        """Test check_if_live() prefixes the message and keeps reason/status/category."""
        mock_youtube_client.videos.list.side_effect = api_error('error_quota_exceeded.json')

        with pytest.raises(APIError, match=r'API error while checking live status') as exc_info:
            check_if_live(mock_youtube_client, ['vid0000001'])

        assert exc_info.value.category is ErrorCategory.QUOTA
        assert exc_info.value.status_code == 403

    @staticmethod
    def test_get_subs_reads_subscriber_counts(mock_youtube_client, quota_tracker):
        """Test get_subs() returns channel_id / subscribers pairs from channels.list."""
        mock_youtube_client.channels.list.return_value = SimpleNamespace(
            items=[SimpleNamespace(id=CHANNEL_ID, statistics=SimpleNamespace(subscriberCount='1234'))]
        )

        result = get_subs(mock_youtube_client, [CHANNEL_ID, None])

        assert result == [{'channel_id': CHANNEL_ID, 'subscribers': '1234'}]
        assert mock_youtube_client.channels.list.call_count == 1
