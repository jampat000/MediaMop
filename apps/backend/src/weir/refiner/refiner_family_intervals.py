"""Refiner-local schedule interval clamps (ADR-0009: not shared with other modules)."""

from __future__ import annotations


def clamp_refiner_schedule_interval_seconds(n: int) -> int:
    """Bound periodic enqueue intervals for Refiner-owned families (60s .. 7d)."""

    return max(60, min(n, 7 * 24 * 3600))


def clamp_refiner_min_file_age_seconds(n: int) -> int:
    """Bound file-age readiness guardrail (0 .. 7d)."""

    return max(0, min(n, 7 * 24 * 3600))
