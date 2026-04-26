"""Activity writes for ``refiner.file.remux_pass.v1``."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from mediamop.platform.activity import constants as C
from mediamop.platform.activity.service import record_activity_event, update_activity_event


def _filename(relative_media_path: str | None) -> str:
    return Path(str(relative_media_path or "")).name or "this file"


def _progress_detail(payload: dict[str, Any]) -> str:
    return json.dumps(payload, separators=(",", ":"), ensure_ascii=True)[:6000]


def record_refiner_file_remux_pass_completed(db: Session, *, title: str, detail: str | None) -> None:
    record_activity_event(
        db,
        event_type=C.REFINER_FILE_REMUX_PASS_COMPLETED,
        module="refiner",
        title=title,
        detail=detail,
    )


def complete_refiner_file_processing_activity(
    db: Session,
    *,
    activity_id: int,
    title: str,
    detail: str | None,
) -> bool:
    row = update_activity_event(
        db,
        activity_id=activity_id,
        event_type=C.REFINER_FILE_REMUX_PASS_COMPLETED,
        title=title,
        detail=detail,
    )
    return row is not None


def record_refiner_file_processing_started(db: Session, *, payload: dict[str, Any]) -> int:
    name = _filename(payload.get("relative_media_path"))
    row = record_activity_event(
        db,
        event_type=C.REFINER_FILE_PROCESSING_PROGRESS,
        module="refiner",
        title=f"Refiner is processing {name}",
        detail=_progress_detail(payload),
    )
    return int(row.id)


def update_refiner_file_processing_progress(
    db: Session,
    *,
    activity_id: int,
    payload: dict[str, Any],
) -> None:
    name = _filename(payload.get("relative_media_path"))
    status = str(payload.get("status") or "processing")
    title = f"Refiner is processing {name}"
    if status == "finishing":
        title = f"Refiner is finishing {name}"
    elif status == "finished":
        title = f"{name} finished processing"
    elif status == "failed":
        title = f"{name} could not be processed"
    update_activity_event(
        db,
        activity_id=activity_id,
        title=title,
        detail=_progress_detail(payload),
    )
