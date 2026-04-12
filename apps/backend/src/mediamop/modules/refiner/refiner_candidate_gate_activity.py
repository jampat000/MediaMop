"""Activity writes for the Refiner candidate gate family."""

from __future__ import annotations

from sqlalchemy.orm import Session

from mediamop.platform.activity import constants as C
from mediamop.platform.activity.service import record_activity_event


def record_refiner_candidate_gate_completed(db: Session, *, detail: str | None) -> None:
    record_activity_event(
        db,
        event_type=C.REFINER_CANDIDATE_GATE_COMPLETED,
        module="refiner",
        title="Refiner candidate gate",
        detail=detail,
    )
