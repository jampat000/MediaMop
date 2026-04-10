"""Refiner worker bounds — shared by :mod:`mediamop.core.config` without import cycles."""


def clamp_refiner_worker_count(raw: int) -> int:
    """Enforce 0..8 workers (0 = no in-process workers; default from config is 1)."""

    if raw < 0:
        return 1
    return min(8, raw)
