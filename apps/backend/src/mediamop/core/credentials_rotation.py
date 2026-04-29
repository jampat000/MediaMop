"""Shared helpers for safe credential-secret rotation."""

from __future__ import annotations

from collections.abc import Callable
from typing import TypeVar

from mediamop.core.config import MediaMopSettings

T = TypeVar("T")


def credential_secret_candidates(settings: MediaMopSettings, build: Callable[[str | None], T | None]) -> list[T]:
    """Return current then previous credential-key handlers, skipping unusable secrets."""

    out: list[T] = []
    for secret in (settings.credentials_secret, *settings.previous_credentials_secrets):
        item = build(secret)
        if item is not None:
            out.append(item)
    return out
