"""Application error types — scaffolding only until domain logic exists."""

from __future__ import annotations


class MediaMopError(Exception):
    """Base exception for MediaMop backend."""


class ConfigurationError(MediaMopError):
    """Raised when required configuration is missing or invalid."""
