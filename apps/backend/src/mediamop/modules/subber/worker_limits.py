"""Subber worker bounds — shared by :mod:`mediamop.core.config` without import cycles."""

from __future__ import annotations


def clamp_subber_worker_count(raw: int) -> int:
    """Enforce 0..8 workers (0 = disabled)."""

    if raw < 0:
        return 0
    return min(8, raw)
