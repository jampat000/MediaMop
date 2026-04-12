"""Activity writes for ``trimmer.supplied_trim_plan.json_file_write.v1``."""

from __future__ import annotations

from sqlalchemy.orm import Session

from mediamop.platform.activity import constants as C
from mediamop.platform.activity.service import record_activity_event


def record_trimmer_supplied_trim_plan_json_file_write_completed(
    db: Session,
    *,
    detail: str | None,
) -> None:
    record_activity_event(
        db,
        event_type=C.TRIMMER_SUPPLIED_TRIM_PLAN_JSON_FILE_WRITE_COMPLETED,
        module="trimmer",
        title="Trimmer supplied trim plan JSON file write",
        detail=detail,
    )
