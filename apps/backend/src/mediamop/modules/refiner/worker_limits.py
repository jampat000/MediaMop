"""Refiner worker bounds — shared by :mod:`mediamop.core.config` without import cycles.

``refiner_worker_count`` is an **internal startup slot cap**, not the number of files
Refiner will work on.

The effective limit is the **runner budget** (#338): a total capacity, and a cost per file
based on its resolution, checked when a job is leased. That replaced a flat "Files at
once" count, which treated a 700 MB SD rip and a 60 GB 4K remux as the same unit of work
and so protected nothing in particular. Small files now cost nothing and run alongside;
the box self-limits on the expensive work, which is the real constraint.

- **0** — In-process Refiner asyncio workers disabled (tests, controlled runtime).
- **1..8** — Available worker slots. The shipped default is **8**
  (``MEDIAMOP_REFINER_WORKER_COUNT``), because the budget is what actually gates
  concurrency; a lower cap here would silently ceiling it.

SQLite still serializes writes, so raising capacity does not scale throughput linearly.
That caveat belongs to the operator-facing budget rather than to this cap — and the budget
is where it can now be expressed honestly, because a capacity in units of expensive work
means something a file count never did.
"""


def clamp_refiner_worker_count(raw: int) -> int:
    """Enforce 0..8 slots (0 = disabled). The env default is 8; negative values mean 1."""

    if raw < 0:
        return 1
    return min(8, raw)
