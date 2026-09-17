"""Activity writes for Refiner Pass 4 failure-cleanup sweeps."""

from __future__ import annotations

import json

from sqlalchemy.orm import Session

from weir.platform.activity import constants as C
from weir.platform.activity.service import record_activity_event


def _with_outcome(detail: str | None, *, result: str, trigger: str | None) -> str | None:
    """The sweep's own detail plus the standard ``result`` and ``trigger`` (#469)."""

    try:
        data = json.loads(detail) if detail else {}
    except ValueError:
        return detail
    if not isinstance(data, dict):
        return detail
    data.setdefault("result", result)
    if trigger:
        data.setdefault("trigger", trigger)
    return json.dumps(data, separators=(",", ":"), ensure_ascii=True)[:10_000]


def record_refiner_failure_cleanup_sweep_completed(
    db: Session,
    *,
    media_scope: str,
    detail: str | None,
    trigger: str | None = None,
) -> None:
    label = "TV" if (media_scope or "").strip().lower() == "tv" else "Movies"
    title = f"Refiner cleaned up after failed files ({label})"
    result = "success"
    if detail and '"cleanup_run_status":"no_eligible_files"' in detail:
        title = f"Refiner cleanup checked {label}: no changes needed"
    elif detail and '"cleanup_run_status":"skipped"' in detail:
        title = f"Refiner cleanup skipped {label}"
        result = "skipped"
    record_activity_event(
        db,
        event_type=C.REFINER_FAILURE_CLEANUP_SWEEP_COMPLETED,
        module="refiner",
        title=title,
        detail=_with_outcome(detail, result=result, trigger=trigger),
    )


def record_refiner_failure_cleanup_sweep_started(
    db: Session,
    *,
    media_scope: str,
    detail: str | None,
    trigger: str | None = None,
) -> None:
    label = "TV" if (media_scope or "").strip().lower() == "tv" else "Movies"
    record_activity_event(
        db,
        event_type=C.REFINER_FAILURE_CLEANUP_SWEEP_COMPLETED,
        module="refiner",
        title=f"Refiner cleanup started for {label}",
        detail=_with_outcome(detail, result="running", trigger=trigger),
    )


def record_refiner_failure_cleanup_sweep_skipped(
    db: Session,
    *,
    media_scope: str,
    detail: str | None,
) -> None:
    label = "TV" if (media_scope or "").strip().lower() == "tv" else "Movies"
    record_activity_event(
        db,
        event_type=C.REFINER_FAILURE_CLEANUP_SWEEP_COMPLETED,
        module="refiner",
        title=f"Refiner cleanup skipped for {label}",
        detail=_with_outcome(detail, result="skipped", trigger="scheduled"),
    )
