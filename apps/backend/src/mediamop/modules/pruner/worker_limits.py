"""Pruner worker bounds — shared by :mod:`mediamop.core.config` without import cycles.

- **0** — in-process Pruner asyncio workers disabled.
- **1** — supported default for SQLite-first deployments.
- **2..8** — guarded only (same posture as Refiner under single-writer SQLite).
"""


def clamp_pruner_worker_count(raw: int) -> int:
    """Enforce 0..8 workers (0 = disabled)."""

    if raw < 0:
        return 0
    return min(8, raw)
