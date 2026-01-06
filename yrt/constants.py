"""Application-wide constants for YouTube Release Tracker."""

# === Video Routing Destinations ===
ROUTING_SHORTS = 'shorts'
ROUTING_NONE = 'none'

# === Live Broadcast Statuses ===
LIVE_STATUS_NONE = 'none'
LIVE_STATUS_UPCOMING = 'upcoming'
LIVE_STATUS_LIVE = 'live'

# === Privacy/Video Statuses ===
STATUS_PUBLIC = 'public'
STATUS_UNLISTED = 'unlisted'
STATUS_PRIVATE = 'private'
STATUS_DELETED = 'deleted'

# === API Error Categories (frozen sets for immutability) ===
TRANSIENT_ERRORS = frozenset({
    'serviceunavailable',
    'backenderror',
    'internalerror',
})
PERMANENT_ERRORS = frozenset({
    'videonotfound',
    'forbidden',
    'playlistoperationunsupported',
    'duplicate',
})
QUOTA_ERRORS = frozenset({'quotaexceeded'})

# === Date/Time Formats ===
ISO_DATE_FORMAT = '%Y-%m-%dT%H:%M:%S%z'
LOG_DATE_FORMAT = '%Y-%m-%d %H:%M:%S%z'

# === YouTube Channel/Playlist ID Prefixes ===
CHANNEL_PREFIX = 'UC'
UPLOAD_PLAYLIST_PREFIX = 'UU'

# === Channel Category Keys (from pocket_tube.json) ===
CATEGORY_MUSIC = 'MUSIQUE'
CATEGORY_LEARNING = 'APPRENTISSAGE'
CATEGORY_ENTERTAINMENT = 'DIVERTISSEMENT'
CATEGORY_GAMING = 'GAMING'
CATEGORY_ASMR = 'ASMR'

# Category priority order for routing
CATEGORY_PRIORITY = (
    CATEGORY_LEARNING,
    CATEGORY_ENTERTAINMENT,
    CATEGORY_GAMING,
    CATEGORY_ASMR,
)
