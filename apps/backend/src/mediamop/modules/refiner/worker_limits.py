"""Refiner worker bounds — shared by :mod:`mediamop.core.config` without import cycles.

``refiner_worker_count`` is an **internal startup slot cap**, not the number of files
Refiner will work on. The effective limit is the operator-facing "Files at once" value on
the Processing settings page, applied at runtime by ``max_concurrent_files_getter``, and
changing it needs no restart.

- **0** — In-process Refiner asyncio workers disabled (tests, controlled runtime).
- **1..8** — Available worker slots. The shipped default is **8**
  (``MEDIAMOP_REFINER_WORKER_COUNT``), because the saved "Files at once" value is what
  actually gates concurrency; a lower cap here would silently ceiling that setting.

SQLite still serializes writes, so raising "Files at once" does not scale throughput
linearly — that caveat belongs to the operator-facing setting, not to this cap.
"""


def clamp_refiner_worker_count(raw: int) -> int:
    """Enforce 0..8 slots (0 = disabled). The env default is 8; negative values mean 1."""

    if raw < 0:
        return 1
    return min(8, raw)
