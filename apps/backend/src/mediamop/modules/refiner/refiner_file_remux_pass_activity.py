"""Activity writes for ``refiner.file.remux_pass.v1``."""

from __future__ import annotations

from sqlalchemy.orm import Session

from mediamop.platform.activity import constants as C
from mediamop.platform.activity.service import record_activity_event


def record_refiner_file_remux_pass_completed(db: Session, *, detail: str | None) -> None:
    record_activity_event(
        db,
        event_type=C.REFINER_FILE_REMUX_PASS_COMPLETED,
        module="refiner",
        title="Refiner file remux pass",
        detail=detail,
    )
