"""Activity feed writes for Subber."""

from __future__ import annotations

import json

from sqlalchemy.orm import Session

from mediamop.platform.activity import constants as C
from mediamop.platform.activity.service import record_activity_event

SUBBER_MODULE = "subber"


def record_subber_activity(
    db: Session,
    *,
    event_type: str,
    title: str,
    detail: dict | None = None,
) -> None:
    record_activity_event(
        db,
        event_type=event_type,
        module=SUBBER_MODULE,
        title=title[:255],
        detail=json.dumps(detail, separators=(",", ":"), default=str)[:50_000] if detail else None,
    )
