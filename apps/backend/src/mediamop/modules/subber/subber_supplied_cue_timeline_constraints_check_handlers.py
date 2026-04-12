"""In-process Subber worker handler for ``subber.supplied_cue_timeline.constraints_check.v1``."""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

from sqlalchemy.orm import Session, sessionmaker

from mediamop.modules.subber.subber_supplied_cue_timeline_constraints_check_activity import (
    record_subber_supplied_cue_timeline_constraints_check_completed,
)
from mediamop.modules.subber.subber_supplied_cue_timeline_constraints_evaluate import (
    evaluate_supplied_cue_timeline_constraints,
)
from mediamop.modules.subber.worker_loop import SubberJobWorkContext


def make_subber_supplied_cue_timeline_constraints_check_handler(
    session_factory: sessionmaker[Session],
) -> Callable[[SubberJobWorkContext], None]:
    """Validate supplied cue intervals in JSON only (no files, no OCR, no mux, no other modules)."""

    def _run(ctx: SubberJobWorkContext) -> None:
        raw = (ctx.payload_json or "").strip()
        if not raw:
            detail_obj: dict[str, Any] = {"job_id": ctx.id, "ok": False, "reason": "missing payload_json"}
            detail = json.dumps(detail_obj, separators=(",", ":"))[:10_000]
            with session_factory() as session:
                with session.begin():
                    record_subber_supplied_cue_timeline_constraints_check_completed(session, detail=detail)
            return

        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            detail_obj = {"job_id": ctx.id, "ok": False, "reason": f"invalid json: {exc}"}
            detail = json.dumps(detail_obj, separators=(",", ":"))[:10_000]
            with session_factory() as session:
                with session.begin():
                    record_subber_supplied_cue_timeline_constraints_check_completed(session, detail=detail)
            return

        if not isinstance(data, dict):
            detail_obj = {"job_id": ctx.id, "ok": False, "reason": "payload must be a JSON object"}
            detail = json.dumps(detail_obj, separators=(",", ":"))[:10_000]
            with session_factory() as session:
                with session.begin():
                    record_subber_supplied_cue_timeline_constraints_check_completed(session, detail=detail)
            return

        ok, reason, ev_detail = evaluate_supplied_cue_timeline_constraints(data)
        detail_obj: dict[str, Any] = {"job_id": ctx.id, "ok": ok}
        if reason:
            detail_obj["reason"] = reason
        detail_obj.update(ev_detail)
        detail = json.dumps(detail_obj, separators=(",", ":"))[:10_000]
        with session_factory() as session:
            with session.begin():
                record_subber_supplied_cue_timeline_constraints_check_completed(session, detail=detail)

    return _run
