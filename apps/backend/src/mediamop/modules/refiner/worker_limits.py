"""Refiner worker bounds — shared by :mod:`mediamop.core.config` without import cycles.

Worker count rollout semantics:

- **0** — In-process Refiner asyncio workers disabled (tests, controlled runtime).
- **1** — Supported default for SQLite-first deployments (single writer; predictable).
- **2..8** — Guarded capability only: claim SQL is atomic, but SQLite remains one writer;
  multi-worker is **not** the normal production posture until ops validate under load.
"""


def clamp_refiner_worker_count(raw: int) -> int:
    """Enforce 0..8 workers (0 = disabled; default from env is 1)."""

    if raw < 0:
        return 1
    return min(8, raw)
