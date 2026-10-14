"""Domain models for YouTube Release Tracker."""

# Standard library
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any

# Local
from .constants import (
    CATEGORY_ASMR,
    CATEGORY_ENTERTAINMENT,
    CATEGORY_GAMING,
    CATEGORY_LEARNING,
    CATEGORY_MUSIC,
    LIVE_STATUS_LIVE,
    LIVE_STATUS_NONE,
    LIVE_STATUS_UPCOMING,
    STATUS_PRIVATE,
    STATUS_PUBLIC,
)

# Non-music categories, in pocket_tube.json order
OTHER_CATEGORIES = (CATEGORY_LEARNING, CATEGORY_ENTERTAINMENT, CATEGORY_GAMING, CATEGORY_ASMR)

# === Configuration Models ===


@dataclass
class PlaylistConfig:
    """Configuration for a YouTube playlist.

    Attributes:
        id: YouTube playlist ID.
        name: Human-readable playlist name.
        description: Playlist description.
        retention_days: Optional retention period in days.
        cleanup_on_end: Whether to cleanup ended streams.
    """

    id: str
    name: str
    description: str
    retention_days: int | None = None
    cleanup_on_end: bool | None = None

    def __post_init__(self) -> None:
        """Validate playlist configuration."""
        if not self.id:
            raise ValueError('Playlist ID cannot be empty')
        if not self.name:
            raise ValueError('Playlist name cannot be empty')
        if self.retention_days is not None and self.retention_days < 0:
            raise ValueError(f'retention_days must be >= 0, got {self.retention_days}')


@dataclass
class AddOnConfig:
    """Additional configuration for channel handling.

    Attributes:
        favorites: Mapping of channel names to IDs for favorite channels.
        playlist_not_found_pass: Channel IDs to ignore if playlist returns 404.
        to_pass: Channel IDs to skip entirely during iteration.
        certified: Certified channel IDs, scanned for lives by the frequent job alongside MUSIQUE.
    """

    favorites: dict[str, str]
    playlist_not_found_pass: list[str] = field(default_factory=list)
    to_pass: list[str] = field(default_factory=list)
    certified: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        """Validate add-on configuration."""
        if not isinstance(self.favorites, dict):
            raise ValueError('favorites must be a dict')


@dataclass(frozen=True)
class AppConfig:
    """The three configuration files, loaded once per run and shared by every job.

    Attributes:
        pocket_tube: Channel IDs by category (pocket_tube.json).
        playlists: Playlist definitions by key (playlists.json).
        add_on: Favorites and channel filters (add-on.json).
    """

    pocket_tube: dict[str, list[str]]
    playlists: dict[str, PlaylistConfig]
    add_on: AddOnConfig

    @property
    def music_channels(self) -> list[str]:
        """Channel IDs of the MUSIQUE category."""
        return list(self.pocket_tube.get(CATEGORY_MUSIC, []))

    @property
    def all_channels(self) -> list[str]:
        """Every tracked channel ID, without duplicates (a channel may sit in several categories)."""
        others = [channel for category in OTHER_CATEGORIES for channel in self.pocket_tube.get(category, [])]
        return list(set(self.music_channels + others))

    @property
    def updates_channels(self) -> list[str]:
        """Channel IDs watched by the frequent job: MUSIQUE then certified, without duplicates, in order."""
        return list(dict.fromkeys(self.music_channels + self.add_on.certified))


# === Video/Playlist Item Models ===


@dataclass
class PlaylistItem:
    """A video item from a YouTube playlist.

    Attributes:
        video_id: YouTube video ID.
        video_title: Video title.
        item_id: Playlist item ID (for deletion).
        release_date: Video release datetime.
        status: Privacy status (public, unlisted, private).
        channel_id: Owner channel ID from API.
        channel_name: Owner channel name from API.
        source_channel_id: Channel ID that was iterated (handles artist channels).
    """

    video_id: str
    video_title: str
    item_id: str
    release_date: datetime
    status: str
    channel_id: str
    channel_name: str
    source_channel_id: str

    def __post_init__(self) -> None:
        """Validate required fields."""
        if not self.video_id:
            raise ValueError('video_id cannot be empty')
        if not self.source_channel_id:
            raise ValueError('source_channel_id cannot be empty')


@dataclass
class VideoStats:
    """Statistics for a YouTube video.

    Attributes:
        video_id: YouTube video ID.
        views: View count.
        likes: Like count.
        comments: Comment count.
        duration: Duration in seconds.
        is_shorts: Whether the video is a YouTube Short.
        live_status: Live broadcast status (none, upcoming, live).
        latest_status: Current privacy status.
    """

    video_id: str
    views: int | None = None
    likes: int | None = None
    comments: int | None = None
    duration: int | None = None
    is_shorts: bool | None = None
    live_status: str | None = None
    latest_status: str = STATUS_PUBLIC

    def __post_init__(self) -> None:
        """Validate video ID."""
        if not self.video_id:
            raise ValueError('video_id cannot be empty')


@dataclass
class VideoData:
    """Combined video data with stats (merged from PlaylistItem + VideoStats).

    This represents the final merged data used for routing and storage.

    Attributes:
        video_id: YouTube video ID.
        video_title: Video title.
        item_id: Playlist item ID.
        release_date: Video release datetime.
        status: Privacy status.
        channel_id: Owner channel ID from API.
        channel_name: Owner channel name from API.
        source_channel_id: Channel ID that was iterated.
        views: View count.
        likes: Like count.
        comments: Comment count.
        duration: Duration in seconds.
        is_shorts: Whether the video is a YouTube Short.
        live_status: Live broadcast status.
        latest_status: Current privacy status.
        dest_playlist: Destination playlist ID (set during routing).
    """

    video_id: str
    video_title: str
    item_id: str
    release_date: datetime
    status: str
    channel_id: str
    channel_name: str
    source_channel_id: str
    views: int | None = None
    likes: int | None = None
    comments: int | None = None
    duration: int | None = None
    is_shorts: bool | None = None
    live_status: str = LIVE_STATUS_NONE
    latest_status: str = STATUS_PUBLIC
    dest_playlist: str | None = None

    @classmethod
    def from_playlist_item_and_stats(cls, item: PlaylistItem, stats: VideoStats) -> 'VideoData':
        """Merge PlaylistItem and VideoStats into VideoData.

        Args:
            item: Playlist item data.
            stats: Video statistics.

        Returns:
            Combined VideoData instance.
        """
        return cls(
            video_id=item.video_id,
            video_title=item.video_title,
            item_id=item.item_id,
            release_date=item.release_date,
            status=item.status,
            channel_id=item.channel_id,
            channel_name=item.channel_name,
            source_channel_id=item.source_channel_id,
            views=stats.views,
            likes=stats.likes,
            comments=stats.comments,
            duration=stats.duration,
            is_shorts=stats.is_shorts,
            live_status=stats.live_status or LIVE_STATUS_NONE,
            latest_status=stats.latest_status,
        )


@dataclass
class PlaylistItemRef:
    """Reference to a playlist item for deletion operations.

    Attributes:
        item_id: Playlist item ID (required for deletion API).
        video_id: YouTube video ID (for logging).
        add_date: Optional date when item was added to playlist.
    """

    item_id: str
    video_id: str
    add_date: datetime | None = None

    def __post_init__(self) -> None:
        """Validate required fields."""
        if not self.item_id:
            raise ValueError('item_id cannot be empty')
        if not self.video_id:
            raise ValueError('video_id cannot be empty')


@dataclass(frozen=True)
class LiveStream:
    """A live or scheduled stream, as returned by videos.list with liveStreamingDetails.

    Attributes:
        video_id: YouTube video ID.
        channel_id: Owner channel ID.
        title: Video title.
        status: Live broadcast status (live, upcoming, none).
        privacy_status: Privacy status (public, unlisted, private).
        concurrent_viewers: Current viewers (live streams only).
        total_views: View count.
        actual_start_time: When the stream went live.
        scheduled_start_time: When the stream is scheduled to start.
    """

    video_id: str
    channel_id: str
    title: str
    status: str
    privacy_status: str = STATUS_PUBLIC
    concurrent_viewers: int | None = None
    total_views: int | None = None
    actual_start_time: datetime | None = None
    scheduled_start_time: datetime | None = None

    def __post_init__(self) -> None:
        """Validate video ID."""
        if not self.video_id:
            raise ValueError('video_id cannot be empty')

    @property
    def is_active(self) -> bool:
        """Whether the stream belongs in the lives playlist (live or upcoming, and not private)."""
        return self.status in (LIVE_STATUS_LIVE, LIVE_STATUS_UPCOMING) and self.privacy_status != STATUS_PRIVATE

    def is_current(self, stale_before: datetime) -> bool:
        """Whether the stream is active and not a stale upcoming one.

        A scheduled stream that never started keeps the upcoming status until its owner deletes it.

        Args:
            stale_before: Upcoming streams scheduled before this time are stale.

        Returns:
            True if the stream belongs in the lives playlist.
        """
        stale = (
            self.status == LIVE_STATUS_UPCOMING
            and self.scheduled_start_time is not None
            and self.scheduled_start_time < stale_before
        )
        return self.is_active and not stale

    @property
    def rank_key(self) -> tuple[int, float, float, float]:
        """Sort key, ascending: lives first by viewers, views, then most recent start; upcoming by soonest start."""
        if self.status == LIVE_STATUS_LIVE:
            started = self.actual_start_time.timestamp() if self.actual_start_time else 0.0
            return 0, -(self.concurrent_viewers or 0), -(self.total_views or 0), -started

        scheduled = self.scheduled_start_time.timestamp() if self.scheduled_start_time else float('inf')
        return 1, scheduled, 0.0, 0.0


# === Helper Functions ===


def to_dict(obj: Any) -> dict[str, Any]:
    """Convert dataclass to dict, handling datetime serialization.

    Args:
        obj: Dataclass instance.

    Returns:
        Dictionary representation.

    Raises:
        TypeError: If obj is not a dataclass.
    """
    from dataclasses import is_dataclass

    if not is_dataclass(obj) or isinstance(obj, type):
        raise TypeError(f'Expected dataclass instance, got {type(obj)}')

    result = asdict(obj)

    # Convert datetime objects to ISO format strings for JSON serialization
    for key, value in result.items():
        if isinstance(value, datetime):
            result[key] = value.isoformat()

    return result


def to_dict_list(items: list[Any]) -> list[dict[str, Any]]:
    """Convert list of dataclasses to list of dicts.

    Args:
        items: List of dataclass instances.

    Returns:
        List of dictionaries.
    """
    return [to_dict(item) for item in items]
