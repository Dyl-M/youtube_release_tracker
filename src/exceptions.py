# -*- coding: utf-8 -*-

"""File Information
@file_name: exceptions.py
@author: Dylan "dyl-m" Monfret
Custom exceptions for the YouTube Release Tracker application.
"""


class YouTubeTrackerError(Exception):
    """Base exception for all YouTube Release Tracker errors."""
    pass


class ConfigurationError(YouTubeTrackerError):
    """Raised when there's an error with configuration files (missing, malformed, invalid keys)."""
    pass


class FileAccessError(YouTubeTrackerError):
    """Raised when file access is denied (path traversal, invalid extension, etc.)."""
    pass


class YouTubeServiceError(YouTubeTrackerError):
    """Raised when YouTube API service creation or operations fail."""
    pass


class CredentialsError(YouTubeTrackerError):
    """Raised when there's an issue with authentication credentials."""
    pass


class APIError(YouTubeTrackerError):
    """Raised when YouTube API calls fail with unrecoverable errors."""
    pass