"""Video routing logic for YouTube Release Tracker."""

# Standard library
from dataclasses import dataclass
from typing import TYPE_CHECKING

# Local
from .constants import (
    ROUTING_SHORTS,
    ROUTING_NONE,
    LIVE_STATUS_UPCOMING,
    CATEGORY_MUSIC,
    CATEGORY_LEARNING,
    CATEGORY_ENTERTAINMENT,
    CATEGORY_GAMING,
    CATEGORY_ASMR,
    CATEGORY_PRIORITY,
)
from .models import PlaylistConfig, AddOnConfig

if TYPE_CHECKING:
    pass

# Module-level default router (set by main.py after config loading)
_default_router: 'VideoRouter | None' = None


# === Configuration ===


@dataclass
class RouterConfig:
    """Configuration for video routing decisions.

    Attributes:
        music_channels: Set of music channel IDs.
        favorite_channels: Set of favorite channel IDs.
        category_channels: Mapping of category names to channel ID sets.
        category_priority: Ordered list of category names for routing priority.
        category_playlists: Mapping of category names to playlist IDs.
        release_radar_id: Release Radar playlist ID.
        banger_radar_id: Banger Radar playlist ID.
        music_lives_id: Music Lives playlist ID.
        regular_streams_id: Regular streams playlist ID.
        long_video_threshold_minutes: Duration threshold for long videos.
    """

    music_channels: set[str]
    favorite_channels: set[str]
    category_channels: dict[str, set[str]]
    category_priority: list[str]
    category_playlists: dict[str, str]
    release_radar_id: str
    banger_radar_id: str
    music_lives_id: str
    regular_streams_id: str
    long_video_threshold_minutes: int = 10

    def __post_init__(self) -> None:
        """Validate configuration."""
        required_ids = [
            ('release_radar_id', self.release_radar_id),
            ('banger_radar_id', self.banger_radar_id),
            ('music_lives_id', self.music_lives_id),
            ('regular_streams_id', self.regular_streams_id),
        ]

        for name, value in required_ids:
            if not value:
                raise ValueError(f"{name} cannot be empty")

        if self.long_video_threshold_minutes <= 0:
            raise ValueError("long_video_threshold_minutes must be positive")


# === Router Class ===


class VideoRouter:
    """Routes videos to appropriate playlists based on channel and video properties.

    The router applies the following priority-based logic:
        1. Upcoming streams -> music_lives (music) or regular_streams (non-music)
        2. Shorts -> 'shorts' (excluded)
        3. Non-music channels -> category playlist by priority
        4. Music channels:
           - Long videos from dual-category -> non-music category playlist
           - Long videos from music-only -> 'none' (skipped)
           - Favorites -> Banger Radar
           - Regular -> Release Radar

    Attributes:
        config: RouterConfig with routing parameters.
    """

    SPECIAL_SHORTS: str = ROUTING_SHORTS
    SPECIAL_NONE: str = ROUTING_NONE

    def __init__(self, config: RouterConfig) -> None:
        """Initialize router with configuration.

        Args:
            config: RouterConfig instance with routing parameters.
        """
        self.config = config

    def route(self, channel_id: str, is_shorts: bool | None,
              duration: int | None, live_status: str = 'none') -> str:
        """Determine destination playlist for a video.

        Args:
            channel_id: Source YouTube channel ID.
            is_shorts: Whether video is a YouTube Short (None if unknown).
            duration: Video duration in seconds (None if unknown).
            live_status: Live broadcast status ('none', 'upcoming', 'live').

        Returns:
            Playlist ID or special string ('shorts', 'none').
        """
        # Step 1: Handle upcoming streams
        if live_status == LIVE_STATUS_UPCOMING:
            return self._route_stream(channel_id)

        # Step 2: Handle shorts
        if is_shorts:
            return self.SPECIAL_SHORTS

        # Step 3: Determine channel properties
        is_music = channel_id in self.config.music_channels
        is_long = self._is_long_video(duration)
        non_music_category = self._get_non_music_category(channel_id)

        # Step 4: Route non-music channels
        if not is_music:
            return self._route_non_music(non_music_category)

        # Step 5: Route music channels
        return self._route_music(channel_id, is_long, non_music_category)

    def _route_stream(self, channel_id: str) -> str:
        """Route upcoming streams to appropriate playlist.

        Args:
            channel_id: Source YouTube channel ID.

        Returns:
            Stream playlist ID.
        """
        if channel_id in self.config.music_channels:
            return self.config.music_lives_id
        return self.config.regular_streams_id

    def _is_long_video(self, duration: int | None) -> bool:
        """Check if video exceeds duration threshold.

        Args:
            duration: Video duration in seconds (None treated as 0).

        Returns:
            True if video is longer than threshold.
        """
        threshold_seconds = self.config.long_video_threshold_minutes * 60
        return (duration or 0) > threshold_seconds

    def _get_non_music_category(self, channel_id: str) -> str | None:
        """Find highest-priority non-music category for channel.

        Args:
            channel_id: Source YouTube channel ID.

        Returns:
            Category name or None if not in any category.
        """
        for category in self.config.category_priority:
            if channel_id in self.config.category_channels.get(category, set()):
                return category
        return None

    def _route_non_music(self, category: str | None) -> str:
        """Route non-music channel video to category playlist.

        Args:
            category: Non-music category name or None.

        Returns:
            Category playlist ID or 'none' special value.
        """
        if category:
            return self.config.category_playlists[category]
        return self.SPECIAL_NONE

    def _route_music(self, channel_id: str, is_long: bool,
                     non_music_category: str | None) -> str:
        """Route music channel video to appropriate playlist.

        Args:
            channel_id: Source YouTube channel ID.
            is_long: Whether video exceeds duration threshold.
            non_music_category: Non-music category name if dual-category channel.

        Returns:
            Destination playlist ID or 'none' special value.
        """
        # Long videos from dual-category channels go to category playlist
        if is_long:
            if non_music_category:
                return self.config.category_playlists[non_music_category]
            return self.SPECIAL_NONE

        # Favorites go to Banger Radar
        if channel_id in self.config.favorite_channels:
            return self.config.banger_radar_id

        # Regular music goes to Release Radar
        return self.config.release_radar_id

    def __call__(self, channel_id: str, is_shorts: bool | None,
                 duration: int | None, live_status: str = 'none') -> str:
        """Allow router instance to be called like a function.

        This enables backward-compatible usage as a drop-in replacement
        for the original dest_playlist function.

        Args:
            channel_id: Source YouTube channel ID.
            is_shorts: Whether video is a YouTube Short.
            duration: Video duration in seconds.
            live_status: Live broadcast status.

        Returns:
            Playlist ID or special string ('shorts', 'none').
        """
        return self.route(channel_id, is_shorts, duration, live_status)


# === Factory Functions ===


def create_router_from_config(
        pocket_tube: dict[str, list[str]],
        playlists: dict[str, PlaylistConfig],
        add_on: AddOnConfig,
        long_video_threshold: int | None = None
) -> VideoRouter:
    """Create a VideoRouter from configuration objects.

    Args:
        pocket_tube: Channel categories from pocket_tube.json.
        playlists: Playlist configurations from playlists.json.
        add_on: Add-on configuration from add-on.json.
        long_video_threshold: Override for long video threshold in minutes.

    Returns:
        Configured VideoRouter instance.
    """
    from . import config as app_config

    threshold = long_video_threshold or app_config.LONG_VIDEO_THRESHOLD_MINUTES

    router_config = RouterConfig(
        music_channels=set(pocket_tube.get(CATEGORY_MUSIC, [])),
        favorite_channels=set(add_on.favorites.values()),
        category_channels={
            CATEGORY_LEARNING: set(pocket_tube.get(CATEGORY_LEARNING, [])),
            CATEGORY_ENTERTAINMENT: set(pocket_tube.get(CATEGORY_ENTERTAINMENT, [])),
            CATEGORY_GAMING: set(pocket_tube.get(CATEGORY_GAMING, [])),
            CATEGORY_ASMR: set(pocket_tube.get(CATEGORY_ASMR, [])),
        },
        category_priority=list(CATEGORY_PRIORITY),
        category_playlists={
            CATEGORY_LEARNING: playlists['apprentissage'].id,
            CATEGORY_ENTERTAINMENT: playlists['divertissement_gaming'].id,
            CATEGORY_GAMING: playlists['divertissement_gaming'].id,
            CATEGORY_ASMR: playlists['asmr'].id,
        },
        release_radar_id=playlists['release'].id,
        banger_radar_id=playlists['banger'].id,
        music_lives_id=playlists['music_lives'].id,
        regular_streams_id=playlists['regular_streams'].id,
        long_video_threshold_minutes=threshold
    )

    return VideoRouter(router_config)


def set_default_router(router: VideoRouter) -> None:
    """Set the module-level default router.

    This should be called by main.py after creating the router from config.

    Args:
        router: VideoRouter instance to use as default.
    """
    global _default_router
    _default_router = router


def dest_playlist(channel_id: str, is_shorts: bool | None, v_duration: int | None,
                  live_status: str = 'none') -> str:
    """Return destination playlist for addition based on channel category and video properties.

    This is a convenience function that uses the default router set by main.py.

    Routing logic:
        1. Upcoming streams -> route to stream playlists (music_lives or regular_streams).
        2. Shorts are always excluded (return 'shorts').
        3. Non-music channels route to category playlists by priority:
           APPRENTISSAGE > DIVERTISSEMENT/GAMING > ASMR.
        4. Music channels:
           - Long videos (>threshold) from dual-category channels -> their non-music category playlist.
           - Long videos (>threshold) from music-only channels -> 'none' (skipped).
           - Favorites -> Banger Radar.
           - Others -> Release Radar.

    Args:
        channel_id: YouTube channel ID.
        is_shorts: Boolean indicating whether the video is a YouTube Short (None if unknown).
        v_duration: YouTube video duration in seconds (None if unknown).
        live_status: YouTube live broadcast content status ('none', 'upcoming', 'live').

    Returns:
        Appropriate YouTube playlist ID or special string ('shorts', 'none').

    Raises:
        RuntimeError: If called before set_default_router().
    """
    if _default_router is None:
        raise RuntimeError("Router not initialized. Call set_default_router() first.")

    return _default_router.route(
        channel_id,
        is_shorts,
        v_duration,
        live_status
    )
