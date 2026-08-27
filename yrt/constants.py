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
TRANSIENT_ERRORS = frozenset(
    {
        'serviceunavailable',
        'backenderror',
        'internalerror',
    }
)
PERMANENT_ERRORS = frozenset(
    {
        'videonotfound',
        'forbidden',
        'playlistoperationunsupported',
        'duplicate',
    }
)
QUOTA_ERRORS = frozenset({'quotaexceeded'})

# === YouTube Data API quota costs (units per call) ===
QUOTA_COST_LIST = 1  # any *.list call, regardless of page size
QUOTA_COST_WRITE = 50  # playlistItems.insert / update / delete

# === Date/Time Formats ===
ISO_DATE_FORMAT = '%Y-%m-%dT%H:%M:%S%z'
LOG_DATE_FORMAT = '%Y-%m-%d %H:%M:%S%z'

# === Jobs and execution modes ===
JOB_DAILY = 'daily'  # python -m yrt.main: subscriptions, stats, cleanups
JOB_UPDATES = 'updates'  # python -m yrt.updates: lives and mixes on the adaptive schedule
JOBS = (JOB_DAILY, JOB_UPDATES)
EXE_MODE_LOCAL = 'local'  # token files, progress bars
EXE_MODE_ACTION = 'action'  # GitHub Actions: base64 credentials from the environment, no progress bars
EXE_MODES = (EXE_MODE_LOCAL, EXE_MODE_ACTION)

# === Log markers (the start marker anchors last_exe.log extraction and the last-exe date parsing) ===
PROCESS_START_MARKER = 'Process started.'
PROCESS_END_MARKER = 'Process ended.'

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
