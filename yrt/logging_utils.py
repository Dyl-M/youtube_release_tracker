"""Logging utilities for consistent logger configuration."""

# Standard library
import logging
import os
from pathlib import Path


def create_file_logger(
        name: str,
        log_file: Path,
        level: int = logging.DEBUG,
        respect_no_logging: bool = True
) -> logging.Logger:
    """Create a standardized file logger.

    Args:
        name: Logger name.
        log_file: Path to log file.
        level: Logging level.
        respect_no_logging: Whether to check YRT_NO_LOGGING environment variable.

    Returns:
        Configured logger instance.
    """
    logger = logging.Logger(name=name, level=0)

    if respect_no_logging and os.environ.get('YRT_NO_LOGGING'):
        return logger

    handler = logging.FileHandler(filename=log_file)
    handler.setLevel(level)

    formatter = logging.Formatter(
        fmt='%(asctime)s [%(levelname)s] - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S%z'
    )

    handler.setFormatter(formatter)
    logger.addHandler(handler)

    return logger
