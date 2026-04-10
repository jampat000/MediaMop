"""Datetime helpers for consistent UTC comparisons (SQLite often returns naive datetimes)."""

from __future__ import annotations

from datetime import datetime, timezone


def as_utc(dt: datetime) -> datetime:
    """Treat naive values as UTC; normalize aware values to UTC."""

    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)
