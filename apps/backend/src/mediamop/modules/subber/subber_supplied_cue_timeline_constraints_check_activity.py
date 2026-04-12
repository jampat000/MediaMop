"""Activity writes for ``subber.supplied_cue_timeline.constraints_check.v1``."""

from __future__ import annotations

from sqlalchemy.orm import Session

from mediamop.platform.activity import constants as C
from mediamop.platform.activity.service import record_activity_event


def record_subber_supplied_cue_timeline_constraints_check_completed(
    db: Session,
    *,
    detail: str | None,
) -> None:
    record_activity_event(
        db,
        event_type=C.SUBBER_SUPPLIED_CUE_TIMELINE_CONSTRAINTS_CHECK_COMPLETED,
        module="subber",
        title="Subber cue timeline constraint check",
        detail=detail,
    )
