# -*- coding: utf-8 -*-

import pytest

from pathlib import Path

from yrt import paths

"""Tests for centralized path definitions."""


@pytest.mark.unit
class TestPathDefinitions:
    """Test path constants and structure."""

    @staticmethod
    def test_base_dir_exists():
        """Test BASE_DIR is defined and exists."""
        assert paths.BASE_DIR is not None
        assert isinstance(paths.BASE_DIR, Path)
        assert paths.BASE_DIR.exists()

    @staticmethod
    def test_directory_paths():
        """Test all directory paths are Path objects."""
        assert isinstance(paths.CONFIG_DIR, Path)
        assert isinstance(paths.DATA_DIR, Path)
        assert isinstance(paths.LOG_DIR, Path)
        assert isinstance(paths.TOKENS_DIR, Path)

    @staticmethod
    def test_file_paths():
        """Test all file paths are Path objects."""
        # Config files
        assert isinstance(paths.POCKET_TUBE_JSON, Path)
        assert isinstance(paths.PLAYLISTS_JSON, Path)
        assert isinstance(paths.ADD_ON_JSON, Path)
        assert isinstance(paths.API_FAILURE_JSON, Path)
        assert isinstance(paths.CONSTANTS_JSON, Path)
        # Data files
        assert isinstance(paths.STATS_CSV, Path)
        # Log files
        assert isinstance(paths.HISTORY_LOG, Path)
        assert isinstance(paths.LAST_EXE_LOG, Path)
        # Token files
        assert isinstance(paths.OAUTH_JSON, Path)
        assert isinstance(paths.CREDENTIALS_JSON, Path)

    @staticmethod
    def test_directory_structure():
        """Test directories have correct names."""
        assert paths.CONFIG_DIR.name == '_config'
        assert paths.DATA_DIR.name == '_data'
        assert paths.LOG_DIR.name == '_log'
        assert paths.TOKENS_DIR.name == '_tokens'

    @staticmethod
    def test_file_paths_in_correct_directories():
        """Test files are located in expected directories."""
        # Config files
        assert paths.POCKET_TUBE_JSON.parent == paths.CONFIG_DIR
        assert paths.PLAYLISTS_JSON.parent == paths.CONFIG_DIR
        assert paths.ADD_ON_JSON.parent == paths.CONFIG_DIR
        assert paths.API_FAILURE_JSON.parent == paths.CONFIG_DIR
        assert paths.CONSTANTS_JSON.parent == paths.CONFIG_DIR

        # Data files
        assert paths.STATS_CSV.parent == paths.DATA_DIR

        # Log files
        assert paths.HISTORY_LOG.parent == paths.LOG_DIR
        assert paths.LAST_EXE_LOG.parent == paths.LOG_DIR

        # Token files
        assert paths.OAUTH_JSON.parent == paths.TOKENS_DIR
        assert paths.CREDENTIALS_JSON.parent == paths.TOKENS_DIR

    @staticmethod
    def test_allowed_dirs_list():
        """Test ALLOWED_DIRS contains expected directories."""
        assert isinstance(paths.ALLOWED_DIRS, list)
        assert len(paths.ALLOWED_DIRS) >= 4
        # Check they're strings (for compatibility with file_utils)
        for allowed_dir in paths.ALLOWED_DIRS:
            assert isinstance(allowed_dir, str)

    @staticmethod
    def test_allowed_extensions_list():
        """Test ALLOWED_EXTENSIONS contains expected extensions."""
        assert isinstance(paths.ALLOWED_EXTENSIONS, list)
        assert '.json' in paths.ALLOWED_EXTENSIONS
        assert '.csv' in paths.ALLOWED_EXTENSIONS
        assert '.log' in paths.ALLOWED_EXTENSIONS

    @staticmethod
    def test_paths_are_absolute():
        """Test all paths are absolute, not relative."""
        assert paths.BASE_DIR.is_absolute()
        assert paths.CONFIG_DIR.is_absolute()
        assert paths.DATA_DIR.is_absolute()
        assert paths.LOG_DIR.is_absolute()
        assert paths.TOKENS_DIR.is_absolute()
