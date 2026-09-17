"""Activity writes for ``refiner.work_temp_stale_sweep.v1``."""

from __future__ import annotations

import json

from sqlalchemy.orm import Session

from weir.platform.activity import constants as C
from weir.platform.activity.service import record_activity_event


def record_refiner_work_temp_stale_sweep_completed(
    db: Session,
    *,
    media_scope: str,
    detail: str | None,
    trigger: str | None = None,
) -> None:
    label = "TV" if (media_scope or "").strip().lower() == "tv" else "Movies"
    title = f"Refiner cleaned up leftover work files ({label})"
    try:
        data = json.loads(detail) if detail else {}
    except ValueError:
        data = {}
    if isinstance(data, dict):
        skipped = bool(data.get("temp_cleanup_skipped_reason")) and not data.get("temp_cleanup_ran")
        if skipped:
            title = f"Refiner left {label} work files alone"
        data.setdefault("result", "skipped" if skipped else "success")
        if trigger:
            data.setdefault("trigger", trigger)
        detail = json.dumps(data, separators=(",", ":"), ensure_ascii=True)[:10_000]
    record_activity_event(
        db,
        event_type=C.REFINER_WORK_TEMP_STALE_SWEEP_COMPLETED,
        module="refiner",
        title=title,
        detail=detail,
    )
