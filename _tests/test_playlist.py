"""Tests for yrt/youtube/playlist.py - Playlist writes through the retry layer and api_failure bookkeeping."""

# Standard library
import json
from types import SimpleNamespace

# Third-party
import pytest
from pyyoutube.error import ErrorMessage, PyYouTubeException

# Local
from yrt.constants import QUOTA_COST_LIST, QUOTA_COST_WRITE
from yrt.models import PlaylistItemRef
from yrt.youtube.playlist import add_api_fail, add_to_playlist, del_from_playlist, fill_release_radar

KNOWN_PLAYLIST = 'PLknown000000000000000000000000000'
STREAM_PLAYLIST = 'PLstream00000000000000000000000000'
UNLISTED_PLAYLIST = 'PLnowhere0000000000000000000000000'
RE_LISTENING = 'PLrelisten000000000000000000000000'
LEGACY = 'PLlegacy00000000000000000000000000'


@pytest.fixture
def api_failure_file(tmp_path, monkeypatch):
    """Point paths.API_FAILURE_JSON at a temp file holding one known playlist with no failures."""
    from yrt import paths

    path = tmp_path / 'api_failure.json'
    path.write_text(
        json.dumps({KNOWN_PLAYLIST: {'name': 'Release Radar', 'description': '', 'failure': []}}), encoding='utf-8'
    )
    monkeypatch.setattr(paths, 'API_FAILURE_JSON', path)
    return path


@pytest.fixture
def playlists_file(tmp_path, monkeypatch):
    """Point paths.PLAYLISTS_JSON at a temp file that knows the stream playlist's name."""
    from yrt import paths

    path = tmp_path / 'playlists.json'
    path.write_text(
        json.dumps({'regular_streams': {'name': 'My streams', 'description': '', 'id': STREAM_PLAYLIST}}),
        encoding='utf-8',
    )
    monkeypatch.setattr(paths, 'PLAYLISTS_JSON', path)
    return path


def _saved(path):
    """Read the whole api_failure.json content."""
    return json.loads(path.read_text(encoding='utf-8'))


def _saved_failures(path, playlist_id):
    """Read the failure list saved for a playlist (empty when the playlist is not in the file)."""
    return _saved(path).get(playlist_id, {}).get('failure', [])


@pytest.mark.unit
@pytest.mark.api
class TestAddToPlaylist:
    """Test add_to_playlist() triage: retried, skipped or saved for the next run."""

    @staticmethod
    def test_success_inserts_each_video(mock_youtube_client, quota_tracker, api_failure_file):
        """Test every video is inserted once, charged 50 units each, and nothing is saved."""
        add_to_playlist(mock_youtube_client, KNOWN_PLAYLIST, ['vid0000001', 'vid0000002'], prog_bar=False)

        assert mock_youtube_client.playlistItems.insert.call_count == 2
        assert quota_tracker.spent == 2 * QUOTA_COST_WRITE
        assert _saved_failures(api_failure_file, KNOWN_PLAYLIST) == []

    @staticmethod
    def test_transient_error_is_retried_and_not_saved(
        mock_youtube_client, quota_tracker, api_failure_file, api_error, no_sleep
    ):
        """Test a transient failure followed by success leaves no trace in api_failure.json."""
        mock_youtube_client.playlistItems.insert.side_effect = [api_error('error_503_backend.json'), None]

        add_to_playlist(mock_youtube_client, KNOWN_PLAYLIST, ['vid0000001'], prog_bar=False)

        assert mock_youtube_client.playlistItems.insert.call_count == 2
        assert no_sleep.call_count == 1
        assert _saved_failures(api_failure_file, KNOWN_PLAYLIST) == []

    @staticmethod
    def test_permanent_error_is_skipped(
        mock_youtube_client, quota_tracker, api_failure_file, api_error, no_sleep, history_mock
    ):
        """Test a permanent error (forbidden) is logged and skipped, never saved, and the loop continues."""
        mock_youtube_client.playlistItems.insert.side_effect = [api_error('error_403_response.json'), None]

        add_to_playlist(mock_youtube_client, KNOWN_PLAYLIST, ['vid0000001', 'vid0000002'], prog_bar=False)

        assert mock_youtube_client.playlistItems.insert.call_count == 2
        assert _saved_failures(api_failure_file, KNOWN_PLAYLIST) == []
        assert any('Permanent error' in call.args[0] for call in history_mock.warning.call_args_list)

    @staticmethod
    def test_quota_error_is_saved_under_existing_entry(
        mock_youtube_client, quota_tracker, api_failure_file, api_error, no_sleep
    ):
        """Test a quota rejection saves the videos under the playlist's existing entry, untouched otherwise."""
        mock_youtube_client.playlistItems.insert.side_effect = api_error('error_quota_exceeded.json')

        add_to_playlist(mock_youtube_client, KNOWN_PLAYLIST, ['vid0000001', 'vid0000002'], prog_bar=False)

        saved = _saved(api_failure_file)[KNOWN_PLAYLIST]
        assert saved['failure'] == ['vid0000001', 'vid0000002']
        assert saved['name'] == 'Release Radar'
        assert quota_tracker.spent == 0

    @staticmethod
    def test_exhausted_transient_retries_are_saved(
        mock_youtube_client, quota_tracker, api_failure_file, api_error, no_sleep
    ):
        """Test a video that keeps failing transiently ends up saved for the next run."""
        mock_youtube_client.playlistItems.insert.side_effect = api_error('error_503_backend.json')

        add_to_playlist(mock_youtube_client, KNOWN_PLAYLIST, ['vid0000001'], prog_bar=False)

        assert _saved_failures(api_failure_file, KNOWN_PLAYLIST) == ['vid0000001']

    @staticmethod
    def test_client_side_error_does_not_crash(mock_youtube_client, quota_tracker, api_failure_file, no_sleep):
        """Test an ErrorMessage-backed exception (no HTTP body) is saved instead of raising AttributeError."""
        mock_youtube_client.playlistItems.insert.side_effect = PyYouTubeException(
            ErrorMessage(status_code=10000, message='HTTP error')
        )

        add_to_playlist(mock_youtube_client, KNOWN_PLAYLIST, ['vid0000001'], prog_bar=False)

        assert _saved_failures(api_failure_file, KNOWN_PLAYLIST) == ['vid0000001']

    @staticmethod
    def test_unlisted_playlist_entry_is_created_with_configured_name(
        mock_youtube_client, quota_tracker, api_failure_file, playlists_file, api_error, no_sleep
    ):
        """Test a playlist missing from api_failure.json gets an entry named from playlists.json."""
        mock_youtube_client.playlistItems.insert.side_effect = api_error('error_quota_exceeded.json')

        add_to_playlist(mock_youtube_client, STREAM_PLAYLIST, ['vid0000001'], prog_bar=False)

        saved = _saved(api_failure_file)
        assert saved[STREAM_PLAYLIST]['name'] == 'My streams'
        assert saved[STREAM_PLAYLIST]['failure'] == ['vid0000001']
        assert saved[KNOWN_PLAYLIST]['failure'] == []  # existing entries untouched

    @staticmethod
    def test_unknown_playlist_falls_back_to_its_id(
        mock_youtube_client, quota_tracker, api_failure_file, playlists_file, api_error, no_sleep
    ):
        """Test a playlist unknown to playlists.json is still recorded, named by its ID."""
        mock_youtube_client.playlistItems.insert.side_effect = api_error('error_quota_exceeded.json')

        add_to_playlist(mock_youtube_client, UNLISTED_PLAYLIST, ['vid0000001'], prog_bar=False)

        assert _saved(api_failure_file)[UNLISTED_PLAYLIST]['name'] == UNLISTED_PLAYLIST

    @staticmethod
    def test_missing_playlists_config_falls_back_to_id(
        mock_youtube_client, quota_tracker, api_failure_file, api_error, no_sleep, tmp_path, monkeypatch
    ):
        """Test name resolution degrades to the ID when playlists.json cannot be read."""
        from yrt import paths

        monkeypatch.setattr(paths, 'PLAYLISTS_JSON', tmp_path / 'missing.json')
        mock_youtube_client.playlistItems.insert.side_effect = api_error('error_quota_exceeded.json')

        add_to_playlist(mock_youtube_client, UNLISTED_PLAYLIST, ['vid0000001'], prog_bar=False)

        assert _saved(api_failure_file)[UNLISTED_PLAYLIST]['name'] == UNLISTED_PLAYLIST

    @staticmethod
    def test_entry_without_failure_list_is_repaired(
        mock_youtube_client, quota_tracker, api_failure_file, api_error, no_sleep
    ):
        """Test an existing entry lacking the 'failure' key gets one instead of raising KeyError."""
        api_failure_file.write_text(json.dumps({KNOWN_PLAYLIST: {'name': 'Release Radar'}}), encoding='utf-8')
        mock_youtube_client.playlistItems.insert.side_effect = api_error('error_quota_exceeded.json')

        add_to_playlist(mock_youtube_client, KNOWN_PLAYLIST, ['vid0000001'], prog_bar=False)

        assert _saved_failures(api_failure_file, KNOWN_PLAYLIST) == ['vid0000001']


@pytest.mark.unit
@pytest.mark.api
class TestDelFromPlaylist:
    """Test del_from_playlist() through the retry layer."""

    @staticmethod
    def test_deletes_refs_and_dicts(mock_youtube_client, quota_tracker):
        """Test both PlaylistItemRef instances and plain dicts are accepted, even mixed."""
        items = [PlaylistItemRef(item_id='item_1', video_id='vid0000001'), {'item_id': 'item_2', 'video_id': 'vid2'}]

        del_from_playlist(mock_youtube_client, KNOWN_PLAYLIST, items, prog_bar=False)

        assert mock_youtube_client.playlistItems.delete.call_count == 2
        assert quota_tracker.spent == 2 * QUOTA_COST_WRITE

    @staticmethod
    def test_error_is_logged_and_loop_continues(mock_youtube_client, quota_tracker, api_error, no_sleep, history_mock):
        """Test a failing delete is warned about and the remaining items are still processed."""
        mock_youtube_client.playlistItems.delete.side_effect = [api_error('error_403_response.json'), None]
        items = [{'item_id': 'item_1', 'video_id': 'vid0000001'}, {'item_id': 'item_2', 'video_id': 'vid0000002'}]

        del_from_playlist(mock_youtube_client, KNOWN_PLAYLIST, items, prog_bar=False)

        assert mock_youtube_client.playlistItems.delete.call_count == 2
        assert history_mock.warning.call_count == 1
        assert 'Deletion Request Failure' in history_mock.warning.call_args.args[0]


def _source_item(video_id, added_at='2020-01-01T00:00:00Z'):
    """Build a source-playlist item as read by fill_release_radar (added long ago by default)."""
    return SimpleNamespace(
        id=f'item_{video_id}',
        contentDetails=SimpleNamespace(videoId=video_id),
        snippet=SimpleNamespace(publishedAt=added_at),
    )


@pytest.mark.unit
@pytest.mark.api
class TestFillReleaseRadar:
    """Test fill_release_radar(): the target count, the source allocation and the degraded paths."""

    @staticmethod
    def test_moves_videos_from_both_sources(mock_youtube_client, quota_tracker, api_failure_file):
        """Test a playlist 2 short of its target pulls one video from each source (added, then removed)."""

        def playlist_items_list(**kwargs):
            """Answer per playlist: 38/40 in the target, one candidate in each source."""
            playlist_id = kwargs['playlist_id']
            if playlist_id == KNOWN_PLAYLIST:
                return SimpleNamespace(items=[object()] * 38)
            if playlist_id == RE_LISTENING:
                return SimpleNamespace(items=[_source_item('relisten01')])
            if playlist_id == LEGACY:
                return SimpleNamespace(items=[_source_item('legacy0001')])
            raise AssertionError(f'unexpected playlist {playlist_id}')

        mock_youtube_client.playlistItems.list.side_effect = playlist_items_list
        mock_youtube_client.playlists.list.return_value = SimpleNamespace(
            items=[SimpleNamespace(contentDetails=SimpleNamespace(itemCount=5))] * 2
        )

        fill_release_radar(mock_youtube_client, KNOWN_PLAYLIST, RE_LISTENING, LEGACY, lmt=40, prog_bar=False)

        inserted = [
            call.kwargs['body']['snippet']['resourceId']['videoId']
            for call in mock_youtube_client.playlistItems.insert.call_args_list
        ]
        assert sorted(inserted) == ['legacy0001', 'relisten01']
        assert mock_youtube_client.playlistItems.delete.call_count == 2
        # 3 playlistItems.list + 1 playlists.list, then 2 inserts + 2 deletes
        assert quota_tracker.spent == 4 * QUOTA_COST_LIST + 4 * QUOTA_COST_WRITE

    @staticmethod
    def test_full_playlist_needs_nothing(mock_youtube_client, quota_tracker, history_mock):
        """Test a playlist at its target stops before touching the sources."""
        mock_youtube_client.playlistItems.list.return_value = SimpleNamespace(items=[object()] * 40)

        fill_release_radar(mock_youtube_client, KNOWN_PLAYLIST, RE_LISTENING, LEGACY, lmt=40, prog_bar=False)

        assert mock_youtube_client.playlists.list.call_count == 0
        assert history_mock.info.call_args.args[0] == 'No addition necessary for Release Radar'
        assert quota_tracker.spent == QUOTA_COST_LIST

    @staticmethod
    def test_quota_error_on_count_degrades_to_nothing(mock_youtube_client, quota_tracker, api_error, history_mock):
        """Test a quota rejection while counting the target logs the quota warning and adds nothing."""
        mock_youtube_client.playlistItems.list.side_effect = api_error('error_quota_exceeded.json')

        fill_release_radar(mock_youtube_client, KNOWN_PLAYLIST, RE_LISTENING, LEGACY, lmt=40, prog_bar=False)

        assert mock_youtube_client.playlists.list.call_count == 0
        assert history_mock.warning.call_args.args[0] == 'API quota exceeded.'

    @staticmethod
    def test_other_error_on_count_degrades_with_generic_warning(
        mock_youtube_client, quota_tracker, api_error, no_sleep, history_mock
    ):
        """Test any other failure while counting the target also adds nothing, with the generic warning."""
        mock_youtube_client.playlistItems.list.side_effect = api_error('error_404_response.json')

        fill_release_radar(mock_youtube_client, KNOWN_PLAYLIST, RE_LISTENING, LEGACY, lmt=40, prog_bar=False)

        assert mock_youtube_client.playlists.list.call_count == 0
        assert history_mock.warning.call_args.args[0] == 'Unknown error: %s'


@pytest.mark.unit
@pytest.mark.api
class TestAddApiFail:
    """Test add_api_fail() replays saved failures."""

    @staticmethod
    def test_replays_saved_failures_and_clears_them(mock_youtube_client, quota_tracker, api_failure_file):
        """Test saved videos are re-inserted and the list is cleared when they succeed."""
        api_failure_file.write_text(
            json.dumps({KNOWN_PLAYLIST: {'name': 'Release Radar', 'failure': ['vid0000001', 'vid0000002']}}),
            encoding='utf-8',
        )

        add_api_fail(mock_youtube_client, prog_bar=False)

        assert mock_youtube_client.playlistItems.insert.call_count == 2
        assert _saved_failures(api_failure_file, KNOWN_PLAYLIST) == []

    @staticmethod
    def test_nothing_to_replay_makes_no_call(mock_youtube_client, quota_tracker, api_failure_file):
        """Test an empty failure list performs no API call."""
        add_api_fail(mock_youtube_client, prog_bar=False)

        assert mock_youtube_client.playlistItems.insert.call_count == 0
        assert quota_tracker.spent == 0
