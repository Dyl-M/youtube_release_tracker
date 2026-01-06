"""Tests for application-wide constants module."""

# Third-party
import pytest

# Local
from yrt.constants import (
    # Routing
    ROUTING_SHORTS,
    ROUTING_NONE,
    # Live statuses
    LIVE_STATUS_NONE,
    LIVE_STATUS_UPCOMING,
    LIVE_STATUS_LIVE,
    # Video statuses
    STATUS_PUBLIC,
    STATUS_UNLISTED,
    STATUS_PRIVATE,
    STATUS_DELETED,
    # Error categories
    TRANSIENT_ERRORS,
    PERMANENT_ERRORS,
    QUOTA_ERRORS,
    # Date formats
    ISO_DATE_FORMAT,
    LOG_DATE_FORMAT,
    # Channel prefixes
    CHANNEL_PREFIX,
    UPLOAD_PLAYLIST_PREFIX,
    # Category constants
    CATEGORY_MUSIC,
    CATEGORY_LEARNING,
    CATEGORY_ENTERTAINMENT,
    CATEGORY_GAMING,
    CATEGORY_ASMR,
    CATEGORY_PRIORITY,
)


@pytest.mark.unit
class TestRoutingConstants:
    """Test video routing destination constants."""

    @staticmethod
    def test_routing_shorts_value():
        """Test ROUTING_SHORTS has correct value."""
        assert ROUTING_SHORTS == 'shorts'

    @staticmethod
    def test_routing_none_value():
        """Test ROUTING_NONE has correct value."""
        assert ROUTING_NONE == 'none'

    @staticmethod
    def test_routing_constants_are_strings():
        """Test routing constants are string type."""
        assert isinstance(ROUTING_SHORTS, str)
        assert isinstance(ROUTING_NONE, str)


@pytest.mark.unit
class TestLiveStatusConstants:
    """Test live broadcast status constants."""

    @staticmethod
    def test_live_status_none_value():
        """Test LIVE_STATUS_NONE has correct value."""
        assert LIVE_STATUS_NONE == 'none'

    @staticmethod
    def test_live_status_upcoming_value():
        """Test LIVE_STATUS_UPCOMING has correct value."""
        assert LIVE_STATUS_UPCOMING == 'upcoming'

    @staticmethod
    def test_live_status_live_value():
        """Test LIVE_STATUS_LIVE has correct value."""
        assert LIVE_STATUS_LIVE == 'live'

    @staticmethod
    def test_live_status_constants_are_strings():
        """Test live status constants are string type."""
        assert isinstance(LIVE_STATUS_NONE, str)
        assert isinstance(LIVE_STATUS_UPCOMING, str)
        assert isinstance(LIVE_STATUS_LIVE, str)


@pytest.mark.unit
class TestVideoStatusConstants:
    """Test video privacy/status constants."""

    @staticmethod
    def test_status_public_value():
        """Test STATUS_PUBLIC has correct value."""
        assert STATUS_PUBLIC == 'public'

    @staticmethod
    def test_status_unlisted_value():
        """Test STATUS_UNLISTED has correct value."""
        assert STATUS_UNLISTED == 'unlisted'

    @staticmethod
    def test_status_private_value():
        """Test STATUS_PRIVATE has correct value."""
        assert STATUS_PRIVATE == 'private'

    @staticmethod
    def test_status_deleted_value():
        """Test STATUS_DELETED has correct value."""
        assert STATUS_DELETED == 'deleted'


@pytest.mark.unit
class TestErrorCategories:
    """Test API error categorization constants."""

    @staticmethod
    def test_transient_errors_is_frozenset():
        """Test TRANSIENT_ERRORS is immutable frozenset."""
        assert isinstance(TRANSIENT_ERRORS, frozenset)

    @staticmethod
    def test_permanent_errors_is_frozenset():
        """Test PERMANENT_ERRORS is immutable frozenset."""
        assert isinstance(PERMANENT_ERRORS, frozenset)

    @staticmethod
    def test_quota_errors_is_frozenset():
        """Test QUOTA_ERRORS is immutable frozenset."""
        assert isinstance(QUOTA_ERRORS, frozenset)

    @staticmethod
    def test_transient_errors_contains_expected():
        """Test TRANSIENT_ERRORS contains expected error types."""
        assert 'serviceunavailable' in TRANSIENT_ERRORS
        assert 'backenderror' in TRANSIENT_ERRORS
        assert 'internalerror' in TRANSIENT_ERRORS

    @staticmethod
    def test_permanent_errors_contains_expected():
        """Test PERMANENT_ERRORS contains expected error types."""
        assert 'videonotfound' in PERMANENT_ERRORS
        assert 'forbidden' in PERMANENT_ERRORS
        assert 'playlistoperationunsupported' in PERMANENT_ERRORS
        assert 'duplicate' in PERMANENT_ERRORS

    @staticmethod
    def test_quota_errors_contains_expected():
        """Test QUOTA_ERRORS contains expected error types."""
        assert 'quotaexceeded' in QUOTA_ERRORS

    @staticmethod
    def test_error_categories_are_disjoint():
        """Test error categories don't overlap."""
        assert TRANSIENT_ERRORS.isdisjoint(PERMANENT_ERRORS)
        assert TRANSIENT_ERRORS.isdisjoint(QUOTA_ERRORS)
        assert PERMANENT_ERRORS.isdisjoint(QUOTA_ERRORS)

    @staticmethod
    def test_error_values_are_lowercase():
        """Test all error values are normalized to lowercase."""
        for error in TRANSIENT_ERRORS:
            assert error == error.lower()
        for error in PERMANENT_ERRORS:
            assert error == error.lower()
        for error in QUOTA_ERRORS:
            assert error == error.lower()


@pytest.mark.unit
class TestDateFormats:
    """Test date/time format string constants."""

    @staticmethod
    def test_iso_date_format_value():
        """Test ISO_DATE_FORMAT has correct value."""
        assert ISO_DATE_FORMAT == '%Y-%m-%dT%H:%M:%S%z'

    @staticmethod
    def test_log_date_format_value():
        """Test LOG_DATE_FORMAT has correct value."""
        assert LOG_DATE_FORMAT == '%Y-%m-%d %H:%M:%S%z'

    @staticmethod
    def test_date_formats_are_strings():
        """Test date format constants are string type."""
        assert isinstance(ISO_DATE_FORMAT, str)
        assert isinstance(LOG_DATE_FORMAT, str)


@pytest.mark.unit
class TestChannelPrefixes:
    """Test YouTube channel/playlist ID prefix constants."""

    @staticmethod
    def test_channel_prefix_value():
        """Test CHANNEL_PREFIX has correct value."""
        assert CHANNEL_PREFIX == 'UC'

    @staticmethod
    def test_upload_playlist_prefix_value():
        """Test UPLOAD_PLAYLIST_PREFIX has correct value."""
        assert UPLOAD_PLAYLIST_PREFIX == 'UU'

    @staticmethod
    def test_prefixes_are_two_chars():
        """Test prefixes are exactly 2 characters."""
        assert len(CHANNEL_PREFIX) == 2
        assert len(UPLOAD_PLAYLIST_PREFIX) == 2


@pytest.mark.unit
class TestCategoryConstants:
    """Test channel category constants."""

    @staticmethod
    def test_category_musique_value():
        """Test CATEGORY_MUSIC has correct value."""
        assert CATEGORY_MUSIC == 'MUSIQUE'

    @staticmethod
    def test_category_apprentissage_value():
        """Test CATEGORY_LEARNING has correct value."""
        assert CATEGORY_LEARNING == 'APPRENTISSAGE'

    @staticmethod
    def test_category_divertissement_value():
        """Test CATEGORY_ENTERTAINMENT has correct value."""
        assert CATEGORY_ENTERTAINMENT == 'DIVERTISSEMENT'

    @staticmethod
    def test_category_gaming_value():
        """Test CATEGORY_GAMING has correct value."""
        assert CATEGORY_GAMING == 'GAMING'

    @staticmethod
    def test_category_asmr_value():
        """Test CATEGORY_ASMR has correct value."""
        assert CATEGORY_ASMR == 'ASMR'

    @staticmethod
    def test_category_priority_is_tuple():
        """Test CATEGORY_PRIORITY is immutable tuple."""
        assert isinstance(CATEGORY_PRIORITY, tuple)

    @staticmethod
    def test_category_priority_order():
        """Test CATEGORY_PRIORITY has correct order."""
        expected = (
            CATEGORY_LEARNING,
            CATEGORY_ENTERTAINMENT,
            CATEGORY_GAMING,
            CATEGORY_ASMR,
        )
        assert CATEGORY_PRIORITY == expected

    @staticmethod
    def test_category_priority_excludes_musique():
        """Test MUSIQUE is not in priority order (music routes differently)."""
        assert CATEGORY_MUSIC not in CATEGORY_PRIORITY


@pytest.mark.unit
class TestBackwardCompatibility:
    """Test backward compatibility with yrt.youtube.utils imports."""

    @staticmethod
    def test_utils_exports_transient_errors():
        """Test TRANSIENT_ERRORS importable from utils."""
        # noinspection PyPep8Naming
        from yrt.youtube.utils import TRANSIENT_ERRORS as utils_errors
        assert utils_errors is TRANSIENT_ERRORS

    @staticmethod
    def test_utils_exports_permanent_errors():
        """Test PERMANENT_ERRORS importable from utils."""
        # noinspection PyPep8Naming
        from yrt.youtube.utils import PERMANENT_ERRORS as utils_errors
        assert utils_errors is PERMANENT_ERRORS

    @staticmethod
    def test_utils_exports_quota_errors():
        """Test QUOTA_ERRORS importable from utils."""
        # noinspection PyPep8Naming
        from yrt.youtube.utils import QUOTA_ERRORS as utils_errors
        assert utils_errors is QUOTA_ERRORS

    @staticmethod
    def test_utils_exports_iso_date_format():
        """Test ISO_DATE_FORMAT importable from utils."""
        # noinspection PyPep8Naming
        from yrt.youtube.utils import ISO_DATE_FORMAT as utils_format
        assert utils_format is ISO_DATE_FORMAT
