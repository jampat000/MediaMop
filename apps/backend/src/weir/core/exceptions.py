"""Application error types — scaffolding only until domain logic exists."""

from __future__ import annotations


class WeirError(Exception):
    """Base exception for Weir backend."""


class ConfigurationError(WeirError):
    """Raised when required configuration is missing or invalid."""
