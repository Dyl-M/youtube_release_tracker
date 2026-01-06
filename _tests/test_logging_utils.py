"""Tests for logging_utils module."""

# Standard library
import logging
import os
from pathlib import Path
from unittest.mock import patch

# Local
from yrt.logging_utils import create_file_logger


class TestCreateFileLogger:
    """Tests for create_file_logger function."""

    @staticmethod
    def test_creates_logger_with_correct_name(tmp_path: Path) -> None:
        """Test that logger is created with the specified name."""
        log_file = tmp_path / "test.log"
        logger = create_file_logger("test_logger", log_file)

        assert logger.name == "test_logger"

    @staticmethod
    def test_creates_logger_with_file_handler(tmp_path: Path) -> None:
        """Test that logger has a file handler when YRT_NO_LOGGING is not set."""
        log_file = tmp_path / "test.log"

        with patch.dict(os.environ, {}, clear=True):
            # Ensure YRT_NO_LOGGING is not set
            os.environ.pop('YRT_NO_LOGGING', None)
            logger = create_file_logger("test_logger", log_file)

        assert len(logger.handlers) == 1
        assert isinstance(logger.handlers[0], logging.FileHandler)

    @staticmethod
    def test_no_handler_when_yrt_no_logging_set(tmp_path: Path) -> None:
        """Test that no file handler is added when YRT_NO_LOGGING is set."""
        log_file = tmp_path / "test.log"

        with patch.dict(os.environ, {'YRT_NO_LOGGING': '1'}):
            logger = create_file_logger("test_logger", log_file)

        assert len(logger.handlers) == 0

    @staticmethod
    def test_respect_no_logging_false_ignores_env_var(tmp_path: Path) -> None:
        """Test that respect_no_logging=False ignores YRT_NO_LOGGING env var."""
        log_file = tmp_path / "test.log"

        with patch.dict(os.environ, {'YRT_NO_LOGGING': '1'}):
            logger = create_file_logger("test_logger", log_file, respect_no_logging=False)

        assert len(logger.handlers) == 1
        assert isinstance(logger.handlers[0], logging.FileHandler)

    @staticmethod
    def test_default_level_is_debug(tmp_path: Path) -> None:
        """Test that the default handler level is DEBUG."""
        log_file = tmp_path / "test.log"

        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop('YRT_NO_LOGGING', None)
            logger = create_file_logger("test_logger", log_file)

        assert logger.handlers[0].level == logging.DEBUG

    @staticmethod
    def test_custom_level(tmp_path: Path) -> None:
        """Test that custom level is applied to handler."""
        log_file = tmp_path / "test.log"

        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop('YRT_NO_LOGGING', None)
            logger = create_file_logger("test_logger", log_file, level=logging.WARNING)

        assert logger.handlers[0].level == logging.WARNING

    @staticmethod
    def test_logger_writes_to_file(tmp_path: Path) -> None:
        """Test that logger actually writes to the specified file."""
        log_file = tmp_path / "test.log"

        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop('YRT_NO_LOGGING', None)
            logger = create_file_logger("test_logger", log_file)
            logger.info("Test message")

            # Flush handler to ensure write
            for handler in logger.handlers:
                handler.flush()

        assert log_file.exists()
        content = log_file.read_text()
        assert "Test message" in content

    @staticmethod
    def test_formatter_format(tmp_path: Path) -> None:
        """Test that the log formatter produces expected format."""
        log_file = tmp_path / "test.log"

        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop('YRT_NO_LOGGING', None)
            logger = create_file_logger("test_logger", log_file)
            logger.warning("Test warning")

            for handler in logger.handlers:
                handler.flush()

        content = log_file.read_text()
        # Check format includes expected components
        assert "[WARNING]" in content
        assert "Test warning" in content

    @staticmethod
    def test_logger_base_level_is_zero(tmp_path: Path) -> None:
        """Test that the logger base level is 0 (logs everything)."""
        log_file = tmp_path / "test.log"
        logger = create_file_logger("test_logger", log_file)

        assert logger.level == 0

    @staticmethod
    def test_multiple_loggers_independent(tmp_path: Path) -> None:
        """Test that multiple loggers with different names are independent."""
        log_file1 = tmp_path / "test1.log"
        log_file2 = tmp_path / "test2.log"

        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop('YRT_NO_LOGGING', None)
            logger1 = create_file_logger("logger1", log_file1)
            logger2 = create_file_logger("logger2", log_file2)

        assert logger1.name != logger2.name
        assert logger1 is not logger2
