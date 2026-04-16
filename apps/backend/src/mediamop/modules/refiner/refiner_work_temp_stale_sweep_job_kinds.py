"""Job kind + dedupe keys for ``refiner.work_temp_stale_sweep.v1`` (per Movies / TV)."""

from __future__ import annotations

from mediamop.modules.refiner.refiner_temp_cleanup import (
    RefinerWorkTempSweepMediaScope,
    normalize_work_temp_sweep_media_scope,
)

REFINER_WORK_TEMP_STALE_SWEEP_JOB_KIND = "refiner.work_temp_stale_sweep.v1"
REFINER_WORK_TEMP_STALE_SWEEP_DEDUPE_KEY_MOVIE = "refiner.work_temp_stale_sweep:v1:movie"
REFINER_WORK_TEMP_STALE_SWEEP_DEDUPE_KEY_TV = "refiner.work_temp_stale_sweep:v1:tv"


def refiner_work_temp_stale_sweep_dedupe_key_for_scope(media_scope: str) -> str:
    """Stable dedupe string for periodic enqueue (one pending row per scope)."""

    ms = normalize_work_temp_sweep_media_scope(media_scope)
    return REFINER_WORK_TEMP_STALE_SWEEP_DEDUPE_KEY_TV if ms == "tv" else REFINER_WORK_TEMP_STALE_SWEEP_DEDUPE_KEY_MOVIE


__all__ = [
    "REFINER_WORK_TEMP_STALE_SWEEP_DEDUPE_KEY_MOVIE",
    "REFINER_WORK_TEMP_STALE_SWEEP_DEDUPE_KEY_TV",
    "REFINER_WORK_TEMP_STALE_SWEEP_JOB_KIND",
    "RefinerWorkTempSweepMediaScope",
    "refiner_work_temp_stale_sweep_dedupe_key_for_scope",
]
