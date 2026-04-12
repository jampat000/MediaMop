"""In-process Refiner worker handler for ``refiner.file.remux_pass.v1``."""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

from sqlalchemy.orm import Session, sessionmaker

from mediamop.core.config import MediaMopSettings
from mediamop.modules.refiner.refiner_file_remux_pass_activity import record_refiner_file_remux_pass_completed
from mediamop.modules.refiner.refiner_file_remux_pass_run import run_refiner_file_remux_pass
from mediamop.modules.refiner.refiner_file_remux_pass_visibility import (
    REMUX_PASS_OUTCOME_FAILED_BEFORE_EXECUTION,
    remux_pass_activity_title,
    remux_pass_result_to_activity_detail,
)
from mediamop.modules.refiner.worker_loop import RefinerJobWorkContext


def _record(session_factory: sessionmaker[Session], *, payload: dict[str, Any]) -> None:
    detail = remux_pass_result_to_activity_detail(payload)
    title = remux_pass_activity_title(payload)
    with session_factory() as session:
        with session.begin():
            record_refiner_file_remux_pass_completed(session, title=title, detail=detail)


def make_refiner_file_remux_pass_handler(
    settings: MediaMopSettings,
    session_factory: sessionmaker[Session],
) -> Callable[[RefinerJobWorkContext], None]:
    """One per-file probe/plan/remux pass; ``dry_run`` defaults in payload (see manual enqueue schema)."""

    def _run(ctx: RefinerJobWorkContext) -> None:
        raw = (ctx.payload_json or "").strip()
        if not raw:
            _record(
                session_factory,
                payload={
                    "job_id": ctx.id,
                    "ok": False,
                    "outcome": REMUX_PASS_OUTCOME_FAILED_BEFORE_EXECUTION,
                    "reason": "missing payload_json",
                },
            )
            return

        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            _record(
                session_factory,
                payload={
                    "job_id": ctx.id,
                    "ok": False,
                    "outcome": REMUX_PASS_OUTCOME_FAILED_BEFORE_EXECUTION,
                    "reason": f"invalid json: {exc}",
                },
            )
            return

        if not isinstance(data, dict):
            _record(
                session_factory,
                payload={
                    "job_id": ctx.id,
                    "ok": False,
                    "outcome": REMUX_PASS_OUTCOME_FAILED_BEFORE_EXECUTION,
                    "reason": "payload must be a JSON object",
                },
            )
            return

        rel = data.get("relative_media_path")
        if not isinstance(rel, str) or not rel.strip():
            _record(
                session_factory,
                payload={
                    "job_id": ctx.id,
                    "ok": False,
                    "outcome": REMUX_PASS_OUTCOME_FAILED_BEFORE_EXECUTION,
                    "reason": "relative_media_path is required",
                },
            )
            return

        dry_run = data.get("dry_run", True)
        if not isinstance(dry_run, bool):
            _record(
                session_factory,
                payload={
                    "job_id": ctx.id,
                    "ok": False,
                    "outcome": REMUX_PASS_OUTCOME_FAILED_BEFORE_EXECUTION,
                    "reason": "dry_run must be a boolean when present",
                    "relative_media_path": rel.strip(),
                },
            )
            return

        result = run_refiner_file_remux_pass(
            settings=settings,
            relative_media_path=rel.strip(),
            dry_run=bool(dry_run),
        )
        result["job_id"] = ctx.id
        _record(session_factory, payload=result)

    return _run
