"""In-process Refiner worker handler for ``refiner.file.remux_pass.v1``."""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

from sqlalchemy.orm import Session, sessionmaker

from mediamop.core.config import MediaMopSettings
from mediamop.modules.refiner.refiner_file_remux_pass_activity import record_refiner_file_remux_pass_completed
from mediamop.modules.refiner.refiner_file_remux_pass_run import (
    remux_pass_result_to_activity_detail,
    run_refiner_file_remux_pass,
)
from mediamop.modules.refiner.worker_loop import RefinerJobWorkContext


def make_refiner_file_remux_pass_handler(
    settings: MediaMopSettings,
    session_factory: sessionmaker[Session],
) -> Callable[[RefinerJobWorkContext], None]:
    """One per-file probe/plan/remux pass; ``dry_run`` defaults in payload (see manual enqueue schema)."""

    def _run(ctx: RefinerJobWorkContext) -> None:
        raw = (ctx.payload_json or "").strip()
        if not raw:
            detail_obj: dict[str, Any] = {"job_id": ctx.id, "ok": False, "reason": "missing payload_json"}
            detail = remux_pass_result_to_activity_detail(detail_obj)
            with session_factory() as session:
                with session.begin():
                    record_refiner_file_remux_pass_completed(session, detail=detail)
            return

        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            detail_obj = {"job_id": ctx.id, "ok": False, "reason": f"invalid json: {exc}"}
            detail = remux_pass_result_to_activity_detail(detail_obj)
            with session_factory() as session:
                with session.begin():
                    record_refiner_file_remux_pass_completed(session, detail=detail)
            return

        if not isinstance(data, dict):
            detail_obj = {"job_id": ctx.id, "ok": False, "reason": "payload must be a JSON object"}
            detail = remux_pass_result_to_activity_detail(detail_obj)
            with session_factory() as session:
                with session.begin():
                    record_refiner_file_remux_pass_completed(session, detail=detail)
            return

        rel = data.get("relative_media_path")
        if not isinstance(rel, str) or not rel.strip():
            detail_obj = {"job_id": ctx.id, "ok": False, "reason": "relative_media_path is required"}
            detail = remux_pass_result_to_activity_detail(detail_obj)
            with session_factory() as session:
                with session.begin():
                    record_refiner_file_remux_pass_completed(session, detail=detail)
            return

        dry_run = data.get("dry_run", True)
        if not isinstance(dry_run, bool):
            detail_obj = {"job_id": ctx.id, "ok": False, "reason": "dry_run must be a boolean when present"}
            detail = remux_pass_result_to_activity_detail(detail_obj)
            with session_factory() as session:
                with session.begin():
                    record_refiner_file_remux_pass_completed(session, detail=detail)
            return

        result = run_refiner_file_remux_pass(
            settings=settings,
            relative_media_path=rel.strip(),
            dry_run=bool(dry_run),
        )
        result["job_id"] = ctx.id
        detail = remux_pass_result_to_activity_detail(result)
        with session_factory() as session:
            with session.begin():
                record_refiner_file_remux_pass_completed(session, detail=detail)

    return _run
