"""In-process Refiner worker handler for ``refiner.file.remux_pass.v1``."""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

from sqlalchemy.orm import Session, sessionmaker

from mediamop.core.config import MediaMopSettings
from mediamop.modules.refiner.refiner_file_remux_pass_activity import (
    complete_refiner_file_processing_activity,
    record_refiner_file_processing_started,
    record_refiner_file_remux_pass_completed,
    update_refiner_file_processing_progress,
)
from mediamop.modules.refiner.refiner_file_remux_pass_run import run_refiner_file_remux_pass
from mediamop.modules.refiner.refiner_operator_settings_service import ensure_refiner_operator_settings_row
from mediamop.modules.refiner.refiner_path_settings_service import resolve_refiner_path_runtime_for_remux
from mediamop.modules.refiner.refiner_remux_rules_settings_service import load_refiner_remux_rules_config
from mediamop.modules.refiner.refiner_file_remux_pass_visibility import (
    REMUX_PASS_OUTCOME_FAILED_BEFORE_EXECUTION,
    remux_pass_activity_title,
    remux_pass_result_to_activity_detail,
)
from mediamop.modules.refiner.worker_loop import RefinerJobWorkContext


def _record(session_factory: sessionmaker[Session], *, payload: dict[str, Any], activity_id: int | None = None) -> None:
    detail = remux_pass_result_to_activity_detail(payload)
    title = remux_pass_activity_title(payload)
    with session_factory() as session:
        with session.begin():
            if activity_id is not None:
                updated = complete_refiner_file_processing_activity(
                    session,
                    activity_id=activity_id,
                    title=title,
                    detail=detail,
                )
                if updated:
                    return
            record_refiner_file_remux_pass_completed(session, title=title, detail=detail)


class RefinerActivityProgressReporter:
    def __init__(self, session_factory: sessionmaker[Session], *, job_id: int) -> None:
        self._session_factory = session_factory
        self._job_id = job_id
        self.activity_id: int | None = None

    def __call__(self, payload: dict[str, Any]) -> None:
        body = {"job_id": self._job_id, **payload}
        with self._session_factory() as session:
            with session.begin():
                if self.activity_id is None:
                    self.activity_id = record_refiner_file_processing_started(session, payload=body)
                else:
                    update_refiner_file_processing_progress(session, activity_id=self.activity_id, payload=body)


def _make_progress_reporter(session_factory: sessionmaker[Session], *, job_id: int) -> RefinerActivityProgressReporter:
    return RefinerActivityProgressReporter(session_factory, job_id=job_id)


def make_refiner_file_remux_pass_handler(
    settings: MediaMopSettings,
    session_factory: sessionmaker[Session],
) -> Callable[[RefinerJobWorkContext], None]:
    """One per-file probe/plan/remux pass (live-only contract)."""

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

        legacy_dry_run = data.get("dry_run", None)
        if legacy_dry_run is not None:
            _record(
                session_factory,
                payload={
                    "job_id": ctx.id,
                    "ok": False,
                    "outcome": REMUX_PASS_OUTCOME_FAILED_BEFORE_EXECUTION,
                    "reason": (
                        "This job payload uses legacy Refiner dry_run, which is no longer supported. "
                        "Re-enqueue without dry_run."
                    ),
                    "relative_media_path": rel.strip(),
                },
            )
            return

        media_scope = data.get("media_scope", "movie")
        if not isinstance(media_scope, str) or media_scope not in ("movie", "tv"):
            media_scope = "movie"

        with session_factory() as session:
            op_settings = ensure_refiner_operator_settings_row(session)
            rules_cfg = load_refiner_remux_rules_config(session, media_scope=media_scope)
            path_runtime, path_err = resolve_refiner_path_runtime_for_remux(
                session,
                settings,
                media_scope=media_scope,
            )
            if path_err is not None:
                _record(
                    session_factory,
                    payload={
                        "job_id": ctx.id,
                        "ok": False,
                        "outcome": REMUX_PASS_OUTCOME_FAILED_BEFORE_EXECUTION,
                        "reason": path_err,
                        "relative_media_path": rel.strip(),
                    },
                )
                return

            progress_reporter = _make_progress_reporter(session_factory, job_id=ctx.id)
            result = run_refiner_file_remux_pass(
                settings=settings,
                path_runtime=path_runtime,
                relative_media_path=rel.strip(),
                rules_config=rules_cfg,
                min_file_age_seconds=op_settings.min_file_age_seconds,
                media_scope=media_scope,
                cleanup_session=session,
                current_job_id=ctx.id,
                progress_reporter=progress_reporter,
            )
            result["job_id"] = ctx.id
        _record(session_factory, payload=result, activity_id=progress_reporter.activity_id)

    return _run
