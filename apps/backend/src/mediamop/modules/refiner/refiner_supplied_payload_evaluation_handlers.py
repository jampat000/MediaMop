"""In-process Refiner worker handler for ``refiner.supplied_payload_evaluation.v1``."""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from typing import Any

from sqlalchemy.orm import Session, sessionmaker

from mediamop.modules.refiner.domain import (
    FileAnchorCandidate,
    RefinerQueueRowView,
    file_is_owned_by_queue,
    should_block_for_upstream,
)
from mediamop.modules.refiner.refiner_supplied_payload_evaluation_activity import (
    record_refiner_supplied_payload_evaluation_completed,
)
from mediamop.modules.refiner.worker_loop import RefinerJobWorkContext


def _row_from_mapping(m: Mapping[str, Any]) -> RefinerQueueRowView:
    return RefinerQueueRowView(
        applies_to_file=bool(m.get("applies_to_file")),
        is_upstream_active=bool(m.get("is_upstream_active")),
        is_import_pending=bool(m.get("is_import_pending")),
        blocking_suppressed_for_import_wait=bool(m.get("blocking_suppressed_for_import_wait")),
        queue_title=m.get("queue_title") if m.get("queue_title") is not None else None,
        queue_year=m.get("queue_year") if m.get("queue_year") is not None else None,
    )


def _parse_payload(payload_json: str | None) -> tuple[list[RefinerQueueRowView], FileAnchorCandidate | None]:
    if not payload_json or not payload_json.strip():
        return [], None
    data = json.loads(payload_json)
    if not isinstance(data, dict):
        msg = "supplied payload evaluation job payload must be a JSON object"
        raise ValueError(msg)
    rows_raw = data.get("rows")
    rows: list[RefinerQueueRowView] = []
    if isinstance(rows_raw, list):
        for item in rows_raw:
            if isinstance(item, dict):
                rows.append(_row_from_mapping(item))
    file_candidate: FileAnchorCandidate | None = None
    file_raw = data.get("file")
    if isinstance(file_raw, dict) and file_raw.get("title") is not None:
        title = str(file_raw["title"])
        year = file_raw.get("year")
        y = int(year) if isinstance(year, int) else None
        file_candidate = FileAnchorCandidate(title=title, year=y)
    return rows, file_candidate


def make_refiner_supplied_payload_evaluation_handler(
    session_factory: sessionmaker[Session],
) -> Callable[[RefinerJobWorkContext], None]:
    """Apply Refiner domain rules to optional JSON ``rows`` + ``file`` only (no *arr or disk I/O)."""

    def _run(ctx: RefinerJobWorkContext) -> None:
        rows, file_candidate = _parse_payload(ctx.payload_json)
        owned = file_is_owned_by_queue(rows, file_candidate=file_candidate)
        blocked = should_block_for_upstream(rows, file_candidate=file_candidate)
        detail_obj: dict[str, object] = {
            "job_id": ctx.id,
            "row_count": len(rows),
            "owned": owned,
            "blocked_upstream": blocked,
        }
        detail = json.dumps(detail_obj, separators=(",", ":"))[:10_000]
        with session_factory() as session:
            with session.begin():
                record_refiner_supplied_payload_evaluation_completed(session, detail=detail)

    return _run
