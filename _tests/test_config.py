# -*- coding: utf-8 -*-

import json
import pytest

"""Tests for yrt/config.py - Centralized configuration loading."""


class TestDeepMerge:
    """Tests for the _deep_merge helper function."""

    def test_deep_merge_simple_override(self):
        """Test that simple values are overridden."""
        from yrt.config import _deep_merge

        defaults = {'a': 1, 'b': 2}
        overrides = {'a': 10}
        result = _deep_merge(defaults, overrides)

        assert result['a'] == 10
        assert result['b'] == 2

    def test_deep_merge_nested_dict(self):
        """Test that nested dictionaries are merged recursively."""
        from yrt.config import _deep_merge

        defaults = {'api': {'batch_size': 50, 'timeout': 5}}
        overrides = {'api': {'batch_size': 100}}
        result = _deep_merge(defaults, overrides)

        assert result['api']['batch_size'] == 100
        assert result['api']['timeout'] == 5

    def test_deep_merge_preserves_defaults(self):
        """Test that missing override keys preserve defaults."""
        from yrt.config import _deep_merge

        defaults = {'a': 1, 'b': {'c': 2, 'd': 3}}
        overrides = {}
        result = _deep_merge(defaults, overrides)

        assert result == defaults

    def test_deep_merge_adds_new_keys(self):
        """Test that new keys from overrides are added."""
        from yrt.config import _deep_merge

        defaults = {'a': 1}
        overrides = {'b': 2}
        result = _deep_merge(defaults, overrides)

        assert result['a'] == 1
        assert result['b'] == 2


class TestLoadConfig:
    """Tests for the load_config function."""

    def test_load_config_with_valid_file(self, tmp_path, monkeypatch):
        """Test loading a valid config file."""
        # Create a test config file
        config_data = {
            'api': {'batch_size': 100},
            'network': {'timeout_seconds': 10}
        }
        config_file = tmp_path / 'config.json'
        with open(config_file, 'w') as f:
            json.dump(config_data, f)

        # Patch paths.CONFIG_JSON and file_utils.ALLOWED_DIRS
        from yrt import paths, file_utils
        monkeypatch.setattr(paths, 'CONFIG_JSON', config_file)
        extended_allowed = file_utils.ALLOWED_DIRS + [str(tmp_path)]
        monkeypatch.setattr(file_utils, 'ALLOWED_DIRS', extended_allowed)

        # Import and test
        from yrt.config import load_config, DEFAULTS, _deep_merge
        result = load_config()

        # Verify merge happened correctly
        expected = _deep_merge(DEFAULTS, config_data)
        assert result['api']['batch_size'] == 100
        assert result['network']['timeout_seconds'] == 10
        # Defaults should be preserved for missing keys
        assert result['api']['max_retries'] == DEFAULTS['api']['max_retries']

    def test_load_config_with_missing_file_uses_defaults(self, tmp_path, monkeypatch):
        """Test that missing config file falls back to defaults."""
        from yrt import paths, file_utils
        from yrt.config import DEFAULTS

        # Point to non-existent file
        nonexistent_file = tmp_path / 'nonexistent.json'
        monkeypatch.setattr(paths, 'CONFIG_JSON', nonexistent_file)
        extended_allowed = file_utils.ALLOWED_DIRS + [str(tmp_path)]
        monkeypatch.setattr(file_utils, 'ALLOWED_DIRS', extended_allowed)

        from yrt.config import load_config
        result = load_config()

        assert result == DEFAULTS

    def test_load_config_partial_override(self, tmp_path, monkeypatch):
        """Test partial config override preserves other defaults."""
        # Create config with only some values
        config_data = {
            'playlists': {'release_radar_target_size': 60}
        }
        config_file = tmp_path / 'config.json'
        with open(config_file, 'w') as f:
            json.dump(config_data, f)

        from yrt import paths, file_utils
        monkeypatch.setattr(paths, 'CONFIG_JSON', config_file)
        extended_allowed = file_utils.ALLOWED_DIRS + [str(tmp_path)]
        monkeypatch.setattr(file_utils, 'ALLOWED_DIRS', extended_allowed)

        from yrt.config import load_config, DEFAULTS
        result = load_config()

        # Overridden value
        assert result['playlists']['release_radar_target_size'] == 60
        # Default values preserved
        assert result['api']['batch_size'] == DEFAULTS['api']['batch_size']
        assert result['stats']['week_deltas'] == DEFAULTS['stats']['week_deltas']


class TestConfigConstants:
    """Tests for module-level configuration constants."""

    def test_api_batch_size_is_integer(self):
        """Test that API_BATCH_SIZE is an integer."""
        from yrt.config import API_BATCH_SIZE
        assert isinstance(API_BATCH_SIZE, int)
        assert API_BATCH_SIZE > 0

    def test_max_retries_is_integer(self):
        """Test that MAX_RETRIES is an integer."""
        from yrt.config import MAX_RETRIES
        assert isinstance(MAX_RETRIES, int)
        assert MAX_RETRIES > 0

    def test_base_delay_is_integer(self):
        """Test that BASE_DELAY is an integer."""
        from yrt.config import BASE_DELAY
        assert isinstance(BASE_DELAY, int)
        assert BASE_DELAY > 0

    def test_max_backoff_is_integer(self):
        """Test that MAX_BACKOFF is an integer."""
        from yrt.config import MAX_BACKOFF
        assert isinstance(MAX_BACKOFF, int)
        assert MAX_BACKOFF > 0

    def test_network_timeout_is_integer(self):
        """Test that NETWORK_TIMEOUT is an integer."""
        from yrt.config import NETWORK_TIMEOUT
        assert isinstance(NETWORK_TIMEOUT, int)
        assert NETWORK_TIMEOUT > 0

    def test_release_radar_target_is_integer(self):
        """Test that RELEASE_RADAR_TARGET is an integer."""
        from yrt.config import RELEASE_RADAR_TARGET
        assert isinstance(RELEASE_RADAR_TARGET, int)
        assert RELEASE_RADAR_TARGET > 0

    def test_relistening_age_weeks_is_integer(self):
        """Test that RELISTENING_AGE_WEEKS is an integer."""
        from yrt.config import RELISTENING_AGE_WEEKS
        assert isinstance(RELISTENING_AGE_WEEKS, int)
        assert RELISTENING_AGE_WEEKS > 0

    def test_long_video_threshold_is_integer(self):
        """Test that LONG_VIDEO_THRESHOLD_MINUTES is an integer."""
        from yrt.config import LONG_VIDEO_THRESHOLD_MINUTES
        assert isinstance(LONG_VIDEO_THRESHOLD_MINUTES, int)
        assert LONG_VIDEO_THRESHOLD_MINUTES > 0

    def test_stats_week_deltas_is_list(self):
        """Test that STATS_WEEK_DELTAS is a list of integers."""
        from yrt.config import STATS_WEEK_DELTAS
        assert isinstance(STATS_WEEK_DELTAS, list)
        assert len(STATS_WEEK_DELTAS) > 0
        assert all(isinstance(x, int) for x in STATS_WEEK_DELTAS)


class TestDefaultValues:
    """Tests to verify default configuration values match expected."""

    def test_default_batch_size(self):
        """Test default API batch size is 50."""
        from yrt.config import DEFAULTS
        assert DEFAULTS['api']['batch_size'] == 50

    def test_default_max_retries(self):
        """Test default max retries is 3."""
        from yrt.config import DEFAULTS
        assert DEFAULTS['api']['max_retries'] == 3

    def test_default_timeout(self):
        """Test default network timeout is 5 seconds."""
        from yrt.config import DEFAULTS
        assert DEFAULTS['network']['timeout_seconds'] == 5

    def test_default_release_radar_target(self):
        """Test default Release Radar target is 40."""
        from yrt.config import DEFAULTS
        assert DEFAULTS['playlists']['release_radar_target_size'] == 40

    def test_default_long_video_threshold(self):
        """Test default long video threshold is 10 minutes."""
        from yrt.config import DEFAULTS
        assert DEFAULTS['video']['long_video_threshold_minutes'] == 10

    def test_default_week_deltas(self):
        """Test default week deltas are [1, 4, 12, 24]."""
        from yrt.config import DEFAULTS
        assert DEFAULTS['stats']['week_deltas'] == [1, 4, 12, 24]
