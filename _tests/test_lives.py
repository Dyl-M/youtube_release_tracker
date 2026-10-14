"""Tests for yrt/youtube/lives.py - Live tab detection, ranking and the lives playlist update."""

# Standard library
import datetime as dt
from types import SimpleNamespace

# Third-party
import pytest

# Local
from yrt.constants import (
    LIVE_STATUS_LIVE,
    LIVE_STATUS_NONE,
    LIVE_STATUS_UPCOMING,
    QUOTA_COST_LIST,
    QUOTA_COST_WRITE,
    STATUS_PRIVATE,
)
from yrt.exceptions import APIError, QuotaExhaustedError
from yrt.models import LiveStream
from yrt.youtube import quota
from yrt.youtube.lives import (
    cap_per_channel,
    find_live_streams,
    get_live_candidates,
    get_live_details,
    live_tab_playlist_id,
    update_lives_playlist,
)

PLAYLIST_ID = 'PLlives00000000000000000000000000'
CHANNEL_A = 'UCaaaaaaaaaaaaaaaaaaaaaa'
CHANNEL_B = 'UCbbbbbbbbbbbbbbbbbbbbbb'
# Upcoming streams scheduled before this are stale; _video() schedules on 2026-10-14 by default
STALE_BEFORE = dt.datetime(2026, 10, 13, tzinfo=dt.UTC)


def _item(video_id):
    """Build a playlistItems.list item with the fields lives.py reads."""
    return SimpleNamespace(id=f'item_{video_id}', contentDetails=SimpleNamespace(videoId=video_id))


def _page(items, next_page=None):
    """Build one playlistItems.list response page."""
    return SimpleNamespace(items=items, nextPageToken=next_page)


def _video(
    video_id,
    status,
    *,
    channel_id=CHANNEL_A,
    viewers=None,
    views=0,
    privacy='public',
    started=None,
    scheduled='2026-10-14T20:00:00Z',
):
    """Build a videos.list item with the snippet, liveStreamingDetails, statistics and status parts."""
    return SimpleNamespace(
        id=video_id,
        snippet=SimpleNamespace(channelId=channel_id, title=f'Title {video_id}', liveBroadcastContent=status),
        liveStreamingDetails=SimpleNamespace(
            concurrentViewers=viewers, actualStartTime=started, scheduledStartTime=scheduled
        ),
        statistics=SimpleNamespace(viewCount=views),
        status=SimpleNamespace(privacyStatus=privacy),
    )


def _videos_response(*videos):
    """Build a videos.list response."""
    return SimpleNamespace(items=list(videos))


def _live(video_id, *, channel_id=CHANNEL_A, viewers=0, status=LIVE_STATUS_LIVE):
    """Build an active LiveStream directly."""
    return LiveStream(
        video_id=video_id, channel_id=channel_id, title=video_id, status=status, concurrent_viewers=viewers
    )


def _inserts(client):
    """Return (video_id, position) for every playlistItems.insert call, in call order."""
    return [
        (call.kwargs['body']['snippet']['resourceId']['videoId'], call.kwargs['body']['snippet']['position'])
        for call in client.playlistItems.insert.call_args_list
    ]


@pytest.fixture
def quota_tracker():
    """Override the shared tracker: a budget large enough that only the budget test hits the guard."""
    tracker = quota.QuotaTracker(budget=2500, daily_quota=10000)
    quota.set_tracker(tracker)
    return tracker


def _deleted_item_ids(client):
    """Return the playlist item IDs passed to playlistItems.delete, in call order."""
    return [call.kwargs['playlist_item_id'] for call in client.playlistItems.delete.call_args_list]


@pytest.mark.unit
class TestLiveStreamModel:
    """Test the LiveStream activity rule (port plan D1) and its rank key."""

    @staticmethod
    @pytest.mark.parametrize(
        ('status', 'privacy', 'active'),
        [
            (LIVE_STATUS_LIVE, 'public', True),
            (LIVE_STATUS_UPCOMING, 'unlisted', True),
            (LIVE_STATUS_NONE, 'public', False),
            (LIVE_STATUS_LIVE, STATUS_PRIVATE, False),
        ],
    )
    def test_is_active(status, privacy, active):
        """Test live and upcoming streams are kept, ended or private ones are not."""
        stream = LiveStream(video_id='v1', channel_id=CHANNEL_A, title='t', status=status, privacy_status=privacy)
        assert stream.is_active is active

    @staticmethod
    @pytest.mark.parametrize(
        ('status', 'scheduled', 'current'),
        [
            (LIVE_STATUS_UPCOMING, dt.datetime(2026, 10, 14, tzinfo=dt.UTC), True),
            (LIVE_STATUS_UPCOMING, dt.datetime(2026, 9, 1, tzinfo=dt.UTC), False),
            (LIVE_STATUS_UPCOMING, None, True),
            (LIVE_STATUS_LIVE, dt.datetime(2026, 9, 1, tzinfo=dt.UTC), True),
            (LIVE_STATUS_NONE, dt.datetime(2026, 10, 14, tzinfo=dt.UTC), False),
        ],
    )
    def test_is_current(status, scheduled, current):
        """Test an upcoming stream scheduled before the threshold is stale; a live one never is."""
        stream = LiveStream(
            video_id='v1', channel_id=CHANNEL_A, title='t', status=status, scheduled_start_time=scheduled
        )
        assert stream.is_current(STALE_BEFORE) is current

    @staticmethod
    def test_rank_key_orders_lives_by_viewers_then_upcoming_by_start():
        """Test lives come first by viewers, then upcoming streams soonest first."""
        soon = LiveStream(
            video_id='soon',
            channel_id=CHANNEL_A,
            title='t',
            status=LIVE_STATUS_UPCOMING,
            scheduled_start_time=dt.datetime(2026, 10, 14, tzinfo=dt.UTC),
        )
        later = LiveStream(
            video_id='later',
            channel_id=CHANNEL_A,
            title='t',
            status=LIVE_STATUS_UPCOMING,
            scheduled_start_time=dt.datetime(2026, 10, 20, tzinfo=dt.UTC),
        )
        streams = [later, _live('small', viewers=10), soon, _live('big', viewers=500)]

        assert [s.video_id for s in sorted(streams, key=lambda s: s.rank_key)] == ['big', 'small', 'soon', 'later']

    @staticmethod
    def test_empty_video_id_rejected():
        """Test a LiveStream needs a video ID."""
        with pytest.raises(ValueError, match='video_id'):
            LiveStream(video_id='', channel_id=CHANNEL_A, title='t', status=LIVE_STATUS_LIVE)


@pytest.mark.unit
@pytest.mark.api
class TestGetLiveCandidates:
    """Test the Live tab listing: one page, 404 and error handling."""

    @staticmethod
    def test_live_tab_playlist_id():
        """Test the UC prefix is swapped for UULV."""
        assert live_tab_playlist_id('UCabc') == 'UULVabc'

    @staticmethod
    def test_returns_video_ids_for_one_unit(mock_youtube_client, quota_tracker):
        """Test the first page's video IDs are returned at a cost of one list call."""
        mock_youtube_client.playlistItems.list.return_value = _page([_item('v1'), _item('v2')], next_page='more')

        assert get_live_candidates(mock_youtube_client, CHANNEL_A) == ['v1', 'v2']
        assert mock_youtube_client.playlistItems.list.call_args.kwargs['playlist_id'] == live_tab_playlist_id(CHANNEL_A)
        assert quota_tracker.spent == QUOTA_COST_LIST

    @staticmethod
    def test_missing_live_tab_is_empty_and_silent(mock_youtube_client, quota_tracker, api_error, history_mock):
        """Test a 404 (channel without a Live tab) yields no candidate and no warning."""
        mock_youtube_client.playlistItems.list.side_effect = api_error('error_404_response.json')

        assert get_live_candidates(mock_youtube_client, CHANNEL_A) == []
        history_mock.warning.assert_not_called()

    @staticmethod
    def test_other_errors_are_logged_and_skipped(mock_youtube_client, quota_tracker, api_error, history_mock):
        """Test a non-404 failure only costs this channel's candidates."""
        mock_youtube_client.playlistItems.list.side_effect = api_error('error_403_response.json')

        assert get_live_candidates(mock_youtube_client, CHANNEL_A) == []
        history_mock.warning.assert_called_once()

    @staticmethod
    def test_quota_rejection_propagates(mock_youtube_client, quota_tracker, api_error):
        """Test a quota rejection stops the detection."""
        mock_youtube_client.playlistItems.list.side_effect = api_error('error_quota_exceeded.json')

        with pytest.raises(QuotaExhaustedError):
            get_live_candidates(mock_youtube_client, CHANNEL_A)


@pytest.mark.unit
@pytest.mark.api
class TestGetLiveDetails:
    """Test the videos.list pass: parsing, batching and de-duplication."""

    @staticmethod
    def test_parses_the_live_fields(mock_youtube_client, quota_tracker):
        """Test every LiveStream field is read from the API parts."""
        mock_youtube_client.videos.list.return_value = _videos_response(
            _video('v1', LIVE_STATUS_LIVE, viewers=42, views=1000, started='2026-10-13T08:00:00Z')
        )

        stream = get_live_details(mock_youtube_client, ['v1'])['v1']

        assert stream == LiveStream(
            video_id='v1',
            channel_id=CHANNEL_A,
            title='Title v1',
            status=LIVE_STATUS_LIVE,
            privacy_status='public',
            concurrent_viewers=42,
            total_views=1000,
            actual_start_time=dt.datetime(2026, 10, 13, 8, tzinfo=dt.UTC),
            scheduled_start_time=dt.datetime(2026, 10, 14, 20, tzinfo=dt.UTC),
        )

    @staticmethod
    def test_batches_by_fifty_without_duplicates(mock_youtube_client, quota_tracker):
        """Test 60 distinct IDs (plus a repeat) cost two calls."""
        mock_youtube_client.videos.list.return_value = _videos_response()
        ids = [f'v{index}' for index in range(60)] + ['v0']

        get_live_details(mock_youtube_client, ids)

        sizes = [len(call.kwargs['video_id']) for call in mock_youtube_client.videos.list.call_args_list]
        assert sizes == [50, 10]
        assert quota_tracker.spent == 2 * QUOTA_COST_LIST

    @staticmethod
    def test_missing_parts_default_to_none(mock_youtube_client, quota_tracker):
        """Test a video without liveStreamingDetails, statistics or status still parses."""
        video = SimpleNamespace(
            id='v1',
            snippet=SimpleNamespace(channelId=None, title=None, liveBroadcastContent=None),
            liveStreamingDetails=None,
            statistics=None,
            status=None,
        )
        mock_youtube_client.videos.list.return_value = _videos_response(video)

        stream = get_live_details(mock_youtube_client, ['v1'])['v1']

        assert (stream.status, stream.privacy_status, stream.concurrent_viewers) == (LIVE_STATUS_NONE, 'public', None)


@pytest.mark.unit
@pytest.mark.api
class TestFindLiveStreams:
    """Test detection across channels: skip list, status filtering and ranking."""

    @staticmethod
    def test_keeps_active_streams_ranked(mock_youtube_client, quota_tracker):
        """Test ended, private and stale videos are dropped, the rest ranked, skipped channels never listed."""
        mock_youtube_client.playlistItems.list.side_effect = [
            _page([_item('live_small'), _item('ended')]),
            _page([_item('live_big'), _item('private'), _item('upcoming'), _item('stale')]),
        ]
        mock_youtube_client.videos.list.return_value = _videos_response(
            _video('live_small', LIVE_STATUS_LIVE, viewers=5),
            _video('ended', LIVE_STATUS_NONE),
            _video('live_big', LIVE_STATUS_LIVE, channel_id=CHANNEL_B, viewers=900),
            _video('private', LIVE_STATUS_LIVE, channel_id=CHANNEL_B, privacy=STATUS_PRIVATE),
            _video('upcoming', LIVE_STATUS_UPCOMING, channel_id=CHANNEL_B),
            _video('stale', LIVE_STATUS_UPCOMING, channel_id=CHANNEL_B, scheduled='2026-09-01T20:00:00Z'),
        )

        lives = find_live_streams(
            mock_youtube_client,
            [CHANNEL_A, 'UCskipped', CHANNEL_B],
            stale_before=STALE_BEFORE,
            to_pass=['UCskipped'],
            prog_bar=False,
        )

        assert [stream.video_id for stream in lives] == ['live_big', 'live_small', 'upcoming']
        assert mock_youtube_client.playlistItems.list.call_count == 2
        assert quota_tracker.spent == 3 * QUOTA_COST_LIST


@pytest.mark.unit
class TestCapPerChannel:
    """Test the per-channel cap (port plan D2)."""

    @staticmethod
    def test_zero_means_no_cap():
        """Test every stream is kept, ranked."""
        streams = [_live('a1', viewers=1), _live('a2', viewers=2)]
        assert [s.video_id for s in cap_per_channel(streams, 0)] == ['a2', 'a1']

    @staticmethod
    def test_keeps_the_best_of_each_channel():
        """Test only the top-k streams of a channel survive, other channels unaffected."""
        streams = [
            _live('a1', viewers=1),
            _live('a2', viewers=3),
            _live('a3', viewers=2),
            _live('b1', channel_id=CHANNEL_B, viewers=0),
        ]
        assert [s.video_id for s in cap_per_channel(streams, 2)] == ['a2', 'a3', 'b1']


@pytest.mark.unit
@pytest.mark.api
class TestUpdateLivesPlaylist:
    """Test the playlist update: removal policy, duplicate prevention, positions and the quota budget."""

    @staticmethod
    def test_empty_playlist_gets_every_live_in_rank_order(mock_youtube_client, quota_tracker):
        """Test inserts follow the ranking, each at the end of what is already there."""
        mock_youtube_client.playlistItems.list.return_value = _page([])
        lives = [_live('big', viewers=9), _live('small', viewers=1)]

        added, removed = update_lives_playlist(
            mock_youtube_client, PLAYLIST_ID, lives, stale_before=STALE_BEFORE, prog_bar=False
        )

        assert (added, removed) == (['big', 'small'], [])
        assert _inserts(mock_youtube_client) == [('big', 0), ('small', 1)]
        mock_youtube_client.videos.list.assert_not_called()  # nothing in the playlist to re-check
        assert quota_tracker.spent == QUOTA_COST_LIST + 2 * QUOTA_COST_WRITE

    @staticmethod
    def test_new_live_is_inserted_at_its_rank(mock_youtube_client, quota_tracker):
        """Test a new stream lands before the first kept item ranked below it."""
        mock_youtube_client.playlistItems.list.return_value = _page([_item('top'), _item('bottom')])
        lives = [_live('top', viewers=100), _live('middle', viewers=50), _live('bottom', viewers=1)]

        update_lives_playlist(mock_youtube_client, PLAYLIST_ID, lives, stale_before=STALE_BEFORE, prog_bar=False)

        assert _inserts(mock_youtube_client) == [('middle', 1)]

    @staticmethod
    def test_items_about_to_be_removed_still_count_for_positions(mock_youtube_client, quota_tracker):
        """Test adds run first, so an ended item still occupies its slot."""
        mock_youtube_client.playlistItems.list.return_value = _page([_item('ended'), _item('kept')])
        mock_youtube_client.videos.list.return_value = _videos_response(_video('ended', LIVE_STATUS_NONE))
        lives = [_live('kept', viewers=1), _live('new', viewers=99)]

        added, removed = update_lives_playlist(
            mock_youtube_client, PLAYLIST_ID, lives, stale_before=STALE_BEFORE, prog_bar=False
        )

        assert _inserts(mock_youtube_client) == [('new', 1)]
        assert (added, removed) == (['new'], ['ended'])

    @staticmethod
    def test_removal_policy(mock_youtube_client, quota_tracker):
        """Test ended, private, deleted and stale items go, upcoming and still-live ones stay (port plan D1)."""
        mock_youtube_client.playlistItems.list.return_value = _page(
            [
                _item('ended'),
                _item('private'),
                _item('deleted'),
                _item('stale'),
                _item('upcoming'),
                _item('undetected_live'),
            ]
        )
        # 'deleted' is absent from the response, as the API does for deleted and private videos
        mock_youtube_client.videos.list.return_value = _videos_response(
            _video('ended', LIVE_STATUS_NONE),
            _video('private', LIVE_STATUS_LIVE, privacy=STATUS_PRIVATE),
            _video('stale', LIVE_STATUS_UPCOMING, scheduled='2026-09-01T20:00:00Z'),
            _video('upcoming', LIVE_STATUS_UPCOMING),
            _video('undetected_live', LIVE_STATUS_LIVE, viewers=3),
        )

        added, removed = update_lives_playlist(
            mock_youtube_client, PLAYLIST_ID, [], stale_before=STALE_BEFORE, prog_bar=False
        )

        assert added == []
        assert removed == ['ended', 'private', 'deleted', 'stale']
        assert _deleted_item_ids(mock_youtube_client) == ['item_ended', 'item_private', 'item_deleted', 'item_stale']

    @staticmethod
    def test_never_inserts_a_duplicate_and_removes_extra_copies(mock_youtube_client, quota_tracker):
        """Test a stream already present is not re-added, and a second copy of it is removed."""
        mock_youtube_client.playlistItems.list.return_value = _page(
            [SimpleNamespace(id='item_1', contentDetails=SimpleNamespace(videoId='live')), _item('live')]
        )

        added, removed = update_lives_playlist(
            mock_youtube_client, PLAYLIST_ID, [_live('live')], stale_before=STALE_BEFORE, prog_bar=False
        )

        assert (added, removed) == ([], ['live'])
        mock_youtube_client.playlistItems.insert.assert_not_called()
        assert _deleted_item_ids(mock_youtube_client) == ['item_live']

    @staticmethod
    def test_reads_every_page_of_the_playlist(mock_youtube_client, quota_tracker):
        """Test an item on the second page is known, so it is not inserted again."""
        mock_youtube_client.playlistItems.list.side_effect = [
            _page([_item('a')], next_page='p2'),
            _page([_item('b')]),
        ]

        update_lives_playlist(
            mock_youtube_client, PLAYLIST_ID, [_live('a'), _live('b')], stale_before=STALE_BEFORE, prog_bar=False
        )

        mock_youtube_client.playlistItems.insert.assert_not_called()

    @staticmethod
    def test_cap_removes_the_weakest_streams(mock_youtube_client, quota_tracker):
        """Test max_per_channel drops items over the cap, keeping the best ranked."""
        mock_youtube_client.playlistItems.list.return_value = _page([_item('weak'), _item('strong')])
        lives = [_live('weak', viewers=1), _live('strong', viewers=9)]

        _, removed = update_lives_playlist(
            mock_youtube_client, PLAYLIST_ID, lives, max_per_channel=1, stale_before=STALE_BEFORE, prog_bar=False
        )

        assert removed == ['weak']

    @staticmethod
    def test_budget_postpones_writes_adds_first(mock_youtube_client, history_mock):
        """Test the job budget pays for adds before removals, the rest waits for the next run."""
        quota.set_tracker(quota.QuotaTracker(budget=1 + 3 * QUOTA_COST_WRITE, daily_quota=10000))
        mock_youtube_client.playlistItems.list.return_value = _page([_item('ended1'), _item('ended2')])
        mock_youtube_client.videos.list.return_value = _videos_response(
            _video('ended1', LIVE_STATUS_NONE), _video('ended2', LIVE_STATUS_NONE)
        )
        lives = [_live('n1', viewers=3), _live('n2', viewers=2)]

        added, removed = update_lives_playlist(
            mock_youtube_client, PLAYLIST_ID, lives, stale_before=STALE_BEFORE, prog_bar=False
        )

        # 2 list units leave 149: both adds fit (100), the 49 left pay for no removal
        assert added == ['n1', 'n2']
        assert removed == []
        message, *params = history_mock.warning.call_args.args
        assert message % tuple(params) == 'Quota budget reached: 2 live removal(s) postponed.'

    @staticmethod
    def test_failed_insert_is_skipped(mock_youtube_client, quota_tracker, api_error, history_mock):
        """Test a rejected insert is logged and does not shift later positions."""
        mock_youtube_client.playlistItems.list.return_value = _page([])
        mock_youtube_client.playlistItems.insert.side_effect = [api_error('error_403_response.json'), None]
        lives = [_live('rejected', viewers=9), _live('next', viewers=1)]

        added, _ = update_lives_playlist(
            mock_youtube_client, PLAYLIST_ID, lives, stale_before=STALE_BEFORE, prog_bar=False
        )

        assert added == ['next']
        assert _inserts(mock_youtube_client) == [('rejected', 0), ('next', 0)]
        history_mock.warning.assert_called_once()

    @staticmethod
    def test_quota_rejection_on_insert_propagates(mock_youtube_client, quota_tracker, api_error):
        """Test a quota rejection stops the update."""
        mock_youtube_client.playlistItems.list.return_value = _page([])
        mock_youtube_client.playlistItems.insert.side_effect = api_error('error_quota_exceeded.json')

        with pytest.raises(QuotaExhaustedError):
            update_lives_playlist(
                mock_youtube_client, PLAYLIST_ID, [_live('v1')], stale_before=STALE_BEFORE, prog_bar=False
            )

    @staticmethod
    def test_failed_delete_is_not_reported(mock_youtube_client, quota_tracker, api_error, history_mock):
        """Test a rejected delete is logged and left out of the removed IDs."""
        mock_youtube_client.playlistItems.list.return_value = _page([_item('ended1'), _item('ended2')])
        mock_youtube_client.videos.list.return_value = _videos_response(
            _video('ended1', LIVE_STATUS_NONE), _video('ended2', LIVE_STATUS_NONE)
        )
        mock_youtube_client.playlistItems.delete.side_effect = [api_error('error_403_response.json'), None]

        _, removed = update_lives_playlist(
            mock_youtube_client, PLAYLIST_ID, [], stale_before=STALE_BEFORE, prog_bar=False
        )

        assert removed == ['ended2']
        assert 'Live removal failure' in history_mock.warning.call_args.args[0]

    @staticmethod
    def test_quota_rejection_on_delete_propagates(mock_youtube_client, quota_tracker, api_error):
        """Test a quota rejection stops the removals instead of calling YouTube for each remaining item."""
        mock_youtube_client.playlistItems.list.return_value = _page([_item('ended1'), _item('ended2')])
        mock_youtube_client.videos.list.return_value = _videos_response(
            _video('ended1', LIVE_STATUS_NONE), _video('ended2', LIVE_STATUS_NONE)
        )
        mock_youtube_client.playlistItems.delete.side_effect = api_error('error_quota_exceeded.json')

        with pytest.raises(QuotaExhaustedError):
            update_lives_playlist(mock_youtube_client, PLAYLIST_ID, [], stale_before=STALE_BEFORE, prog_bar=False)

        assert mock_youtube_client.playlistItems.delete.call_count == 1

    @staticmethod
    def test_unreadable_playlist_aborts(mock_youtube_client, quota_tracker, api_error):
        """Test a failed listing raises instead of working from a partial view (duplicates)."""
        mock_youtube_client.playlistItems.list.side_effect = api_error('error_403_response.json')

        with pytest.raises(APIError):
            update_lives_playlist(
                mock_youtube_client, PLAYLIST_ID, [_live('v1')], stale_before=STALE_BEFORE, prog_bar=False
            )

        mock_youtube_client.playlistItems.insert.assert_not_called()
