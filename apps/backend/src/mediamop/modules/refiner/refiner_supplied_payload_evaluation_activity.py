"""Activity writes for ``refiner.supplied_payload_evaluation.v1``."""

from __future__ import annotations

from sqlalchemy.orm import Session

from mediamop.platform.activity import constants as C
from mediamop.platform.activity.service import record_activity_event


def record_refiner_supplied_payload_evaluation_completed(db: Session, *, detail: str | None) -> None:
    record_activity_event(
        db,
        event_type=C.REFINER_SUPPLIED_PAYLOAD_EVALUATION_COMPLETED,
        module="refiner",
        title="Refiner supplied payload evaluation",
        detail=detail,
    )
