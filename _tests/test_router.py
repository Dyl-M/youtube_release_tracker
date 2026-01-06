"""Tests for yrt/router.py - Video routing logic."""

# Third-party
import pytest

# Local
from yrt.router import RouterConfig, VideoRouter, create_router_from_config
from yrt.models import PlaylistConfig, AddOnConfig


# === Fixtures ===


@pytest.fixture
def sample_router_config():
    """Create a sample RouterConfig for testing."""
    return RouterConfig(
        music_channels={'UC_music_1', 'UC_music_2', 'UC_dual_category'},
        favorite_channels={'UC_music_1'},
        category_channels={
            'APPRENTISSAGE': {'UC_learn_1', 'UC_dual_category'},
            'DIVERTISSEMENT': {'UC_fun_1'},
            'GAMING': {'UC_game_1'},
            'ASMR': {'UC_asmr_1'},
        },
        category_priority=['APPRENTISSAGE', 'DIVERTISSEMENT', 'GAMING', 'ASMR'],
        category_playlists={
            'APPRENTISSAGE': 'PL_apprentissage',
            'DIVERTISSEMENT': 'PL_divertissement',
            'GAMING': 'PL_divertissement',
            'ASMR': 'PL_asmr',
        },
        release_radar_id='PL_release',
        banger_radar_id='PL_banger',
        music_lives_id='PL_music_lives',
        regular_streams_id='PL_regular_streams',
        long_video_threshold_minutes=10
    )


@pytest.fixture
def router(sample_router_config):
    """Create a VideoRouter instance for testing."""
    return VideoRouter(sample_router_config)


# === RouterConfig Tests ===


@pytest.mark.unit
class TestRouterConfig:
    """Tests for RouterConfig dataclass."""

    @staticmethod
    def test_creation_with_valid_data(sample_router_config):
        """Test RouterConfig creation with valid data."""
        assert sample_router_config.release_radar_id == 'PL_release'
        assert sample_router_config.long_video_threshold_minutes == 10

    @staticmethod
    def test_validation_empty_release_radar():
        """Test validation rejects empty release_radar_id."""
        with pytest.raises(ValueError, match="release_radar_id cannot be empty"):
            RouterConfig(
                music_channels=set(),
                favorite_channels=set(),
                category_channels={},
                category_priority=[],
                category_playlists={},
                release_radar_id='',
                banger_radar_id='PL_banger',
                music_lives_id='PL_lives',
                regular_streams_id='PL_streams'
            )

    @staticmethod
    def test_validation_empty_banger_radar():
        """Test validation rejects empty banger_radar_id."""
        with pytest.raises(ValueError, match="banger_radar_id cannot be empty"):
            RouterConfig(
                music_channels=set(),
                favorite_channels=set(),
                category_channels={},
                category_priority=[],
                category_playlists={},
                release_radar_id='PL_release',
                banger_radar_id='',
                music_lives_id='PL_lives',
                regular_streams_id='PL_streams'
            )

    @staticmethod
    def test_validation_empty_music_lives():
        """Test validation rejects empty music_lives_id."""
        with pytest.raises(ValueError, match="music_lives_id cannot be empty"):
            RouterConfig(
                music_channels=set(),
                favorite_channels=set(),
                category_channels={},
                category_priority=[],
                category_playlists={},
                release_radar_id='PL_release',
                banger_radar_id='PL_banger',
                music_lives_id='',
                regular_streams_id='PL_streams'
            )

    @staticmethod
    def test_validation_empty_regular_streams():
        """Test validation rejects empty regular_streams_id."""
        with pytest.raises(ValueError, match="regular_streams_id cannot be empty"):
            RouterConfig(
                music_channels=set(),
                favorite_channels=set(),
                category_channels={},
                category_priority=[],
                category_playlists={},
                release_radar_id='PL_release',
                banger_radar_id='PL_banger',
                music_lives_id='PL_lives',
                regular_streams_id=''
            )

    @staticmethod
    def test_validation_zero_threshold():
        """Test validation rejects zero threshold."""
        with pytest.raises(ValueError, match="long_video_threshold_minutes must be positive"):
            RouterConfig(
                music_channels=set(),
                favorite_channels=set(),
                category_channels={},
                category_priority=[],
                category_playlists={},
                release_radar_id='PL_release',
                banger_radar_id='PL_banger',
                music_lives_id='PL_lives',
                regular_streams_id='PL_streams',
                long_video_threshold_minutes=0
            )

    @staticmethod
    def test_validation_negative_threshold():
        """Test validation rejects negative threshold."""
        with pytest.raises(ValueError, match="long_video_threshold_minutes must be positive"):
            RouterConfig(
                music_channels=set(),
                favorite_channels=set(),
                category_channels={},
                category_priority=[],
                category_playlists={},
                release_radar_id='PL_release',
                banger_radar_id='PL_banger',
                music_lives_id='PL_lives',
                regular_streams_id='PL_streams',
                long_video_threshold_minutes=-5
            )


# === VideoRouter Shorts Tests ===


@pytest.mark.unit
class TestVideoRouterShorts:
    """Tests for shorts detection and routing."""

    @staticmethod
    def test_shorts_return_special_value(router):
        """Test that shorts return 'shorts' destination."""
        result = router.route('UC_music_1', is_shorts=True, duration=60)
        assert result == 'shorts'

    @staticmethod
    def test_shorts_none_treated_as_not_shorts(router):
        """Test that is_shorts=None is treated as not a short."""
        result = router.route('UC_music_2', is_shorts=None, duration=120)
        assert result == 'PL_release'

    @staticmethod
    def test_shorts_takes_precedence_over_music(router):
        """Test shorts detection happens before music routing."""
        result = router.route('UC_music_1', is_shorts=True, duration=30)
        assert result == 'shorts'

    @staticmethod
    def test_shorts_from_non_music_channel(router):
        """Test shorts from non-music channel also return 'shorts'."""
        result = router.route('UC_learn_1', is_shorts=True, duration=60)
        assert result == 'shorts'


# === VideoRouter Stream Tests ===


@pytest.mark.unit
class TestVideoRouterStreams:
    """Tests for upcoming stream routing."""

    @staticmethod
    def test_upcoming_music_stream_to_music_lives(router):
        """Test upcoming streams from music channels go to music_lives."""
        result = router.route('UC_music_1', is_shorts=False, duration=None,
                              live_status='upcoming')
        assert result == 'PL_music_lives'

    @staticmethod
    def test_upcoming_nonmusic_stream_to_regular(router):
        """Test upcoming streams from non-music channels go to regular_streams."""
        result = router.route('UC_learn_1', is_shorts=False, duration=None,
                              live_status='upcoming')
        assert result == 'PL_regular_streams'

    @staticmethod
    def test_stream_routing_takes_precedence_over_shorts(router):
        """Test stream routing happens before shorts check."""
        # Even if is_shorts=True, upcoming stream should go to stream playlist
        result = router.route('UC_music_1', is_shorts=True, duration=None,
                              live_status='upcoming')
        assert result == 'PL_music_lives'

    @staticmethod
    def test_live_status_none_bypasses_stream_routing(router):
        """Test live_status='none' does not trigger stream routing."""
        result = router.route('UC_music_2', is_shorts=False, duration=120,
                              live_status='none')
        assert result == 'PL_release'

    @staticmethod
    def test_live_status_live_bypasses_stream_routing(router):
        """Test live_status='live' does not trigger stream routing."""
        # Currently active streams are treated as regular videos
        result = router.route('UC_music_2', is_shorts=False, duration=120,
                              live_status='live')
        assert result == 'PL_release'


# === VideoRouter Non-Music Channel Tests ===


@pytest.mark.unit
class TestVideoRouterNonMusic:
    """Tests for non-music channel routing."""

    @staticmethod
    def test_apprentissage_channel_routes_correctly(router):
        """Test APPRENTISSAGE category channels route to educational playlist."""
        result = router.route('UC_learn_1', is_shorts=False, duration=300)
        assert result == 'PL_apprentissage'

    @staticmethod
    def test_divertissement_channel_routes_correctly(router):
        """Test DIVERTISSEMENT category channels route correctly."""
        result = router.route('UC_fun_1', is_shorts=False, duration=300)
        assert result == 'PL_divertissement'

    @staticmethod
    def test_gaming_channel_routes_to_divertissement(router):
        """Test GAMING shares playlist with DIVERTISSEMENT."""
        result = router.route('UC_game_1', is_shorts=False, duration=300)
        assert result == 'PL_divertissement'

    @staticmethod
    def test_asmr_channel_routes_correctly(router):
        """Test ASMR category channels route correctly."""
        result = router.route('UC_asmr_1', is_shorts=False, duration=300)
        assert result == 'PL_asmr'

    @staticmethod
    def test_unknown_nonmusic_channel_returns_none(router):
        """Test unknown non-music channels return 'none'."""
        result = router.route('UC_unknown', is_shorts=False, duration=300)
        assert result == 'none'

    @staticmethod
    def test_category_priority_order(router):
        """Test channels use first matching category by priority."""
        # UC_dual_category is in both music and APPRENTISSAGE
        # For non-music routing, this tests APPRENTISSAGE gets priority
        result = router.route('UC_learn_1', is_shorts=False, duration=300)
        assert result == 'PL_apprentissage'


# === VideoRouter Music Channel Tests ===


@pytest.mark.unit
class TestVideoRouterMusic:
    """Tests for music channel routing."""

    @staticmethod
    def test_favorite_music_to_banger_radar(router):
        """Test favorite music channel videos go to Banger Radar."""
        result = router.route('UC_music_1', is_shorts=False, duration=180)
        assert result == 'PL_banger'

    @staticmethod
    def test_regular_music_to_release_radar(router):
        """Test regular music channel videos go to Release Radar."""
        result = router.route('UC_music_2', is_shorts=False, duration=180)
        assert result == 'PL_release'

    @staticmethod
    def test_long_music_video_music_only_returns_none(router):
        """Test long videos from music-only channels return 'none'."""
        # Duration > 10 minutes (600 seconds), music-only channel
        result = router.route('UC_music_2', is_shorts=False, duration=700)
        assert result == 'none'

    @staticmethod
    def test_long_music_video_dual_category_routes_to_category(router):
        """Test long videos from dual-category channels route to category."""
        # UC_dual_category is in both music and APPRENTISSAGE
        result = router.route('UC_dual_category', is_shorts=False, duration=700)
        assert result == 'PL_apprentissage'

    @staticmethod
    def test_duration_threshold_exact_boundary(router):
        """Test behavior at exact threshold boundary."""
        # Exactly 10 minutes (600 seconds) should NOT be "long"
        result = router.route('UC_music_2', is_shorts=False, duration=600)
        assert result == 'PL_release'

    @staticmethod
    def test_duration_threshold_just_over(router):
        """Test behavior just over threshold."""
        # 601 seconds should be "long"
        result = router.route('UC_music_2', is_shorts=False, duration=601)
        assert result == 'none'

    @staticmethod
    def test_none_duration_treated_as_short(router):
        """Test None duration is treated as 0 (not long)."""
        result = router.route('UC_music_2', is_shorts=False, duration=None)
        assert result == 'PL_release'

    @staticmethod
    def test_favorite_long_video_still_routes_to_category(router):
        """Test long videos from favorites also follow long video rules."""
        # UC_music_1 is a favorite but if long and music-only, still returns 'none'
        # (UC_music_1 is not in any category, so should return 'none')
        result = router.route('UC_music_1', is_shorts=False, duration=700)
        assert result == 'none'

    @staticmethod
    def test_dual_category_regular_video_routes_to_release_radar(router):
        """Test regular-length videos from dual-category channels go to Release Radar.

        UC_dual_category is in both MUSIQUE and APPRENTISSAGE. Regular-length
        videos should follow music routing (not the category playlist).
        """
        # Regular video (<= 10 min) from dual-category channel
        result = router.route('UC_dual_category', is_shorts=False, duration=300)
        assert result == 'PL_release'


# === VideoRouter Callable Tests ===


@pytest.mark.unit
class TestVideoRouterCallable:
    """Tests for __call__ functionality."""

    @staticmethod
    def test_callable_matches_route(router):
        """Test __call__ produces same result as route()."""
        route_result = router.route('UC_music_1', False, 180, 'none')
        call_result = router('UC_music_1', False, 180, 'none')
        assert route_result == call_result

    @staticmethod
    def test_callable_default_live_status(router):
        """Test __call__ with default live_status."""
        result = router('UC_music_1', False, 180)
        assert result == 'PL_banger'

    @staticmethod
    def test_callable_with_all_parameters(router):
        """Test __call__ with all parameters specified."""
        result = router('UC_learn_1', False, 300, 'none')
        assert result == 'PL_apprentissage'


# === Factory Function Tests ===


@pytest.mark.unit
class TestCreateRouterFromConfig:
    """Tests for create_router_from_config factory."""

    @staticmethod
    def test_creates_router_successfully():
        """Test factory creates router with valid config."""
        pocket_tube = {
            'MUSIQUE': ['UC_music'],
            'APPRENTISSAGE': ['UC_learn'],
            'DIVERTISSEMENT': [],
            'GAMING': [],
        }
        playlists = {
            'release': PlaylistConfig(id='PL_rel', name='Release', description=''),
            'banger': PlaylistConfig(id='PL_ban', name='Banger', description=''),
            'apprentissage': PlaylistConfig(id='PL_app', name='Learn', description=''),
            'divertissement_gaming': PlaylistConfig(id='PL_fun', name='Fun', description=''),
            'asmr': PlaylistConfig(id='PL_asmr', name='ASMR', description=''),
            'music_lives': PlaylistConfig(id='PL_lives', name='Lives', description=''),
            'regular_streams': PlaylistConfig(id='PL_streams', name='Streams', description=''),
        }
        add_on = AddOnConfig(favorites={'Artist': 'UC_music'})

        router = create_router_from_config(pocket_tube, playlists, add_on)

        assert isinstance(router, VideoRouter)
        assert 'UC_music' in router.config.music_channels
        assert 'UC_music' in router.config.favorite_channels

    @staticmethod
    def test_uses_default_threshold(monkeypatch):
        """Test factory uses config.LONG_VIDEO_THRESHOLD_MINUTES by default."""
        from yrt import config
        monkeypatch.setattr(config, 'LONG_VIDEO_THRESHOLD_MINUTES', 15)

        pocket_tube = {'MUSIQUE': [], 'APPRENTISSAGE': [], 'DIVERTISSEMENT': [], 'GAMING': []}
        playlists = {
            'release': PlaylistConfig(id='PL1', name='R', description=''),
            'banger': PlaylistConfig(id='PL2', name='B', description=''),
            'apprentissage': PlaylistConfig(id='PL3', name='A', description=''),
            'divertissement_gaming': PlaylistConfig(id='PL4', name='D', description=''),
            'asmr': PlaylistConfig(id='PL5', name='AS', description=''),
            'music_lives': PlaylistConfig(id='PL6', name='ML', description=''),
            'regular_streams': PlaylistConfig(id='PL7', name='RS', description=''),
        }
        add_on = AddOnConfig(favorites={})

        router = create_router_from_config(pocket_tube, playlists, add_on)

        assert router.config.long_video_threshold_minutes == 15

    @staticmethod
    def test_custom_threshold_override():
        """Test factory accepts custom threshold override."""
        pocket_tube = {'MUSIQUE': [], 'APPRENTISSAGE': [], 'DIVERTISSEMENT': [], 'GAMING': []}
        playlists = {
            'release': PlaylistConfig(id='PL1', name='R', description=''),
            'banger': PlaylistConfig(id='PL2', name='B', description=''),
            'apprentissage': PlaylistConfig(id='PL3', name='A', description=''),
            'divertissement_gaming': PlaylistConfig(id='PL4', name='D', description=''),
            'asmr': PlaylistConfig(id='PL5', name='AS', description=''),
            'music_lives': PlaylistConfig(id='PL6', name='ML', description=''),
            'regular_streams': PlaylistConfig(id='PL7', name='RS', description=''),
        }
        add_on = AddOnConfig(favorites={})

        router = create_router_from_config(
            pocket_tube, playlists, add_on, long_video_threshold=20
        )

        assert router.config.long_video_threshold_minutes == 20

    @staticmethod
    def test_handles_missing_asmr_category():
        """Test factory handles missing ASMR category gracefully."""
        pocket_tube = {
            'MUSIQUE': ['UC_music'],
            'APPRENTISSAGE': ['UC_learn'],
            'DIVERTISSEMENT': [],
            'GAMING': [],
            # No ASMR key
        }
        playlists = {
            'release': PlaylistConfig(id='PL1', name='R', description=''),
            'banger': PlaylistConfig(id='PL2', name='B', description=''),
            'apprentissage': PlaylistConfig(id='PL3', name='A', description=''),
            'divertissement_gaming': PlaylistConfig(id='PL4', name='D', description=''),
            'asmr': PlaylistConfig(id='PL5', name='AS', description=''),
            'music_lives': PlaylistConfig(id='PL6', name='ML', description=''),
            'regular_streams': PlaylistConfig(id='PL7', name='RS', description=''),
        }
        add_on = AddOnConfig(favorites={})

        router = create_router_from_config(pocket_tube, playlists, add_on)

        assert router.config.category_channels['ASMR'] == set()


# === VideoRouter Constants Tests ===


@pytest.mark.unit
class TestVideoRouterConstants:
    """Tests for router class constants."""

    @staticmethod
    def test_special_shorts_value(router):
        """Test SPECIAL_SHORTS constant value."""
        assert router.SPECIAL_SHORTS == 'shorts'

    @staticmethod
    def test_special_none_value(router):
        """Test SPECIAL_NONE constant value."""
        assert router.SPECIAL_NONE == 'none'
