"""Activity writes for Refiner Pass 4 failure-cleanup sweeps."""

from __future__ import annotations

from sqlalchemy.orm import Session

from mediamop.platform.activity import constants as C
from mediamop.platform.activity.service import record_activity_event


def record_refiner_failure_cleanup_sweep_completed(
    db: Session,
    *,
    media_scope: str,
    detail: str | None,
) -> None:
    label = "TV" if (media_scope or "").strip().lower() == "tv" else "Movies"
    title = f"Refiner failed remux cleanup sweep ({label})"
    if detail and '"cleanup_run_status":"no_eligible_files"' in detail:
        title = f"Refiner cleanup checked {label}: no eligible files"
    elif detail and '"cleanup_run_status":"skipped"' in detail:
        title = f"Refiner cleanup skipped {label}"
    record_activity_event(
        db,
        event_type=C.REFINER_FAILURE_CLEANUP_SWEEP_COMPLETED,
        module="refiner",
        title=title,
        detail=detail,
    )


def record_refiner_failure_cleanup_sweep_started(
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
        title=f"Refiner cleanup started for {label}",
        detail=detail,
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
        detail=detail,
    )

