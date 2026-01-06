"""Tests for domain models (dataclasses)."""

# Standard library
from datetime import datetime

# Third-party
import pytest

# Local
from yrt.models import (
    PlaylistConfig,
    AddOnConfig,
    PlaylistItem,
    VideoStats,
    VideoData,
    PlaylistItemRef,
    to_dict,
    to_dict_list
)


# === PlaylistConfig Tests ===


def test_playlist_config_creation():
    """Test PlaylistConfig creation with valid data."""
    config = PlaylistConfig(
        id='PL123',
        name='Test Playlist',
        description='Test Description',
        retention_days=7,
        cleanup_on_end=True
    )
    assert config.id == 'PL123'
    assert config.name == 'Test Playlist'
    assert config.description == 'Test Description'
    assert config.retention_days == 7
    assert config.cleanup_on_end is True


def test_playlist_config_optional_fields():
    """Test PlaylistConfig with optional fields omitted."""
    config = PlaylistConfig(
        id='PL123',
        name='Test Playlist',
        description='Test Description'
    )
    assert config.retention_days is None
    assert config.cleanup_on_end is None


def test_playlist_config_validation_empty_id():
    """Test PlaylistConfig raises ValueError for empty ID."""
    with pytest.raises(ValueError, match="Playlist ID cannot be empty"):
        PlaylistConfig(
            id='',
            name='Test Playlist',
            description='Test Description'
        )


def test_playlist_config_validation_empty_name():
    """Test PlaylistConfig raises ValueError for empty name."""
    with pytest.raises(ValueError, match="Playlist name cannot be empty"):
        PlaylistConfig(
            id='PL123',
            name='',
            description='Test Description'
        )


def test_playlist_config_validation_negative_retention():
    """Test PlaylistConfig raises ValueError for negative retention_days."""
    with pytest.raises(ValueError, match="retention_days must be >= 0"):
        PlaylistConfig(
            id='PL123',
            name='Test Playlist',
            description='Test Description',
            retention_days=-1
        )


# === AddOnConfig Tests ===


def test_addon_config_creation():
    """Test AddOnConfig creation with all fields."""
    config = AddOnConfig(
        favorites={'Artist1': 'UC123', 'Artist2': 'UC456'},
        playlist_not_found_pass=['UC789'],
        to_pass=['UC999'],
        certified=['UC111']
    )
    assert config.favorites == {'Artist1': 'UC123', 'Artist2': 'UC456'}
    assert config.playlist_not_found_pass == ['UC789']
    assert config.to_pass == ['UC999']
    assert config.certified == ['UC111']


def test_addon_config_defaults():
    """Test AddOnConfig with default values for optional fields."""
    config = AddOnConfig(favorites={'Artist1': 'UC123'})
    assert config.favorites == {'Artist1': 'UC123'}
    assert config.playlist_not_found_pass == []
    assert config.to_pass == []
    assert config.certified == []


def test_addon_config_validation_invalid_favorites():
    """Test AddOnConfig raises ValueError for non-dict favorites."""
    with pytest.raises(ValueError, match="favorites must be a dict"):
        AddOnConfig(favorites=['not', 'a', 'dict'])  # type: ignore[arg-type]


# === PlaylistItem Tests ===


def test_playlist_item_creation():
    """Test PlaylistItem creation with valid data."""
    release_date = datetime(2024, 1, 15, 12, 0, 0)
    item = PlaylistItem(
        video_id='vid123',
        video_title='Test Video',
        item_id='item456',
        release_date=release_date,
        status='public',
        channel_id='UC789',
        channel_name='Test Channel',
        source_channel_id='UC999'
    )
    assert item.video_id == 'vid123'
    assert item.video_title == 'Test Video'
    assert item.item_id == 'item456'
    assert item.release_date == release_date
    assert item.status == 'public'
    assert item.channel_id == 'UC789'
    assert item.channel_name == 'Test Channel'
    assert item.source_channel_id == 'UC999'


def test_playlist_item_validation_empty_video_id():
    """Test PlaylistItem raises ValueError for empty video_id."""
    with pytest.raises(ValueError, match="video_id cannot be empty"):
        PlaylistItem(
            video_id='',
            video_title='Test',
            item_id='item123',
            release_date=datetime.now(),
            status='public',
            channel_id='UC123',
            channel_name='Test',
            source_channel_id='UC456'
        )


def test_playlist_item_validation_empty_source_channel():
    """Test PlaylistItem raises ValueError for empty source_channel_id."""
    with pytest.raises(ValueError, match="source_channel_id cannot be empty"):
        PlaylistItem(
            video_id='vid123',
            video_title='Test',
            item_id='item123',
            release_date=datetime.now(),
            status='public',
            channel_id='UC123',
            channel_name='Test',
            source_channel_id=''
        )


# === VideoStats Tests ===


def test_video_stats_creation():
    """Test VideoStats creation with all fields."""
    stats = VideoStats(
        video_id='vid123',
        views=1000,
        likes=50,
        comments=10,
        duration=300,
        is_shorts=False,
        live_status='none',
        latest_status='public'
    )
    assert stats.video_id == 'vid123'
    assert stats.views == 1000
    assert stats.likes == 50
    assert stats.comments == 10
    assert stats.duration == 300
    assert stats.is_shorts is False
    assert stats.live_status == 'none'
    assert stats.latest_status == 'public'


def test_video_stats_defaults():
    """Test VideoStats with default values for optional fields."""
    stats = VideoStats(video_id='vid123')
    assert stats.video_id == 'vid123'
    assert stats.views is None
    assert stats.likes is None
    assert stats.comments is None
    assert stats.duration is None
    assert stats.is_shorts is None
    assert stats.live_status is None
    assert stats.latest_status == 'public'


def test_video_stats_validation_empty_video_id():
    """Test VideoStats raises ValueError for empty video_id."""
    with pytest.raises(ValueError, match="video_id cannot be empty"):
        VideoStats(video_id='')


# === VideoData Tests ===


def test_video_data_creation():
    """Test VideoData creation with all fields."""
    release_date = datetime(2024, 1, 15, 12, 0, 0)
    data = VideoData(
        video_id='vid123',
        video_title='Test Video',
        item_id='item456',
        release_date=release_date,
        status='public',
        channel_id='UC789',
        channel_name='Test Channel',
        source_channel_id='UC999',
        views=1000,
        likes=50,
        comments=10,
        duration=300,
        is_shorts=False,
        live_status='none',
        latest_status='public',
        dest_playlist='PL123'
    )
    assert data.video_id == 'vid123'
    assert data.views == 1000
    assert data.dest_playlist == 'PL123'


def test_video_data_factory_method():
    """Test VideoData.from_playlist_item_and_stats() factory method."""
    release_date = datetime(2024, 1, 15, 12, 0, 0)

    item = PlaylistItem(
        video_id='vid123',
        video_title='Test Video',
        item_id='item456',
        release_date=release_date,
        status='public',
        channel_id='UC789',
        channel_name='Test Channel',
        source_channel_id='UC999'
    )

    stats = VideoStats(
        video_id='vid123',
        views=1000,
        likes=50,
        comments=10,
        duration=300,
        is_shorts=False,
        live_status='upcoming',
        latest_status='public'
    )

    data = VideoData.from_playlist_item_and_stats(item, stats)

    # Check PlaylistItem fields
    assert data.video_id == 'vid123'
    assert data.video_title == 'Test Video'
    assert data.item_id == 'item456'
    assert data.release_date == release_date
    assert data.status == 'public'
    assert data.channel_id == 'UC789'
    assert data.channel_name == 'Test Channel'
    assert data.source_channel_id == 'UC999'

    # Check VideoStats fields
    assert data.views == 1000
    assert data.likes == 50
    assert data.comments == 10
    assert data.duration == 300
    assert data.is_shorts is False
    assert data.live_status == 'upcoming'
    assert data.latest_status == 'public'

    # dest_playlist should be None (not set by factory)
    assert data.dest_playlist is None


def test_video_data_factory_none_live_status():
    """Test factory method handles None live_status by defaulting to 'none'."""
    item = PlaylistItem(
        video_id='vid123',
        video_title='Test',
        item_id='item456',
        release_date=datetime.now(),
        status='public',
        channel_id='UC789',
        channel_name='Test',
        source_channel_id='UC999'
    )

    stats = VideoStats(
        video_id='vid123',
        live_status=None
    )

    data = VideoData.from_playlist_item_and_stats(item, stats)
    assert data.live_status == 'none'


# === PlaylistItemRef Tests ===


def test_playlist_item_ref_creation():
    """Test PlaylistItemRef creation with all fields."""
    add_date = datetime(2024, 1, 15, 12, 0, 0)
    ref = PlaylistItemRef(
        item_id='item123',
        video_id='vid456',
        add_date=add_date
    )
    assert ref.item_id == 'item123'
    assert ref.video_id == 'vid456'
    assert ref.add_date == add_date


def test_playlist_item_ref_without_add_date():
    """Test PlaylistItemRef creation without optional add_date."""
    ref = PlaylistItemRef(
        item_id='item123',
        video_id='vid456'
    )
    assert ref.item_id == 'item123'
    assert ref.video_id == 'vid456'
    assert ref.add_date is None


def test_playlist_item_ref_validation_empty_item_id():
    """Test PlaylistItemRef raises ValueError for empty item_id."""
    with pytest.raises(ValueError, match="item_id cannot be empty"):
        PlaylistItemRef(item_id='', video_id='vid123')


def test_playlist_item_ref_validation_empty_video_id():
    """Test PlaylistItemRef raises ValueError for empty video_id."""
    with pytest.raises(ValueError, match="video_id cannot be empty"):
        PlaylistItemRef(item_id='item123', video_id='')


# === Helper Functions Tests ===


def test_to_dict_with_playlist_config():
    """Test to_dict() converts PlaylistConfig to dict."""
    config = PlaylistConfig(
        id='PL123',
        name='Test Playlist',
        description='Test Description',
        retention_days=7
    )
    result = to_dict(config)

    assert isinstance(result, dict)
    assert result['id'] == 'PL123'
    assert result['name'] == 'Test Playlist'
    assert result['description'] == 'Test Description'
    assert result['retention_days'] == 7
    assert result['cleanup_on_end'] is None


def test_to_dict_with_datetime():
    """Test to_dict() converts datetime fields to ISO format strings."""
    release_date = datetime(2024, 1, 15, 12, 30, 45)
    item = PlaylistItem(
        video_id='vid123',
        video_title='Test',
        item_id='item456',
        release_date=release_date,
        status='public',
        channel_id='UC789',
        channel_name='Test',
        source_channel_id='UC999'
    )
    result = to_dict(item)

    assert isinstance(result, dict)
    assert isinstance(result['release_date'], str)
    assert result['release_date'] == '2024-01-15T12:30:45'


def test_to_dict_non_dataclass_raises_error():
    """Test to_dict() raises TypeError for non-dataclass input."""
    with pytest.raises(TypeError, match="Expected dataclass"):
        to_dict({'not': 'a dataclass'})  # type: ignore[arg-type]


def test_to_dict_list():
    """Test to_dict_list() converts list of dataclasses to list of dicts."""
    items = [
        PlaylistItemRef(item_id='item1', video_id='vid1'),
        PlaylistItemRef(item_id='item2', video_id='vid2'),
        PlaylistItemRef(item_id='item3', video_id='vid3')
    ]

    result = to_dict_list(items)

    assert isinstance(result, list)
    assert len(result) == 3
    assert all(isinstance(d, dict) for d in result)
    assert result[0]['item_id'] == 'item1'
    assert result[1]['video_id'] == 'vid2'
    assert result[2]['item_id'] == 'item3'


def test_to_dict_list_empty():
    """Test to_dict_list() handles empty list."""
    result = to_dict_list([])
    assert result == []
