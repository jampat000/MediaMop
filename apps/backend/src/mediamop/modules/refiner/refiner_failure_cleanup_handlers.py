"""Refiner worker handlers for Pass 4 failure-cleanup sweep jobs."""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

from sqlalchemy.orm import Session, sessionmaker

from mediamop.core.config import MediaMopSettings
from mediamop.modules.refiner.refiner_failure_cleanup import run_refiner_failure_cleanup_sweep_for_scope
from mediamop.modules.refiner.refiner_failure_cleanup_activity import (
    record_refiner_failure_cleanup_sweep_completed,
    record_refiner_failure_cleanup_sweep_started,
)
from mediamop.modules.refiner.worker_loop import RefinerJobWorkContext


def _parse_payload(payload_json: str | None, *, default_scope: str) -> str:
    media_scope = default_scope
    if payload_json and payload_json.strip():
        data = json.loads(payload_json)
        if isinstance(data, dict):
            if str(data.get("media_scope") or "").strip().lower() == "tv":
                media_scope = "tv"
            else:
                media_scope = "movie"
    return media_scope


def make_refiner_failure_cleanup_handler(
    settings: MediaMopSettings,
    session_factory: sessionmaker[Session],
    *,
    default_scope: str,
) -> Callable[[RefinerJobWorkContext], None]:
    def _run(ctx: RefinerJobWorkContext) -> None:
        media_scope = _parse_payload(ctx.payload_json, default_scope=default_scope)
        with session_factory() as session:
            with session.begin():
                record_refiner_failure_cleanup_sweep_started(
                    session,
                    media_scope=media_scope,
                    detail=json.dumps(
                        {"job_id": ctx.id, "media_scope": media_scope, "cleanup_run_status": "started"},
                        separators=(",", ":"),
                        ensure_ascii=True,
                    ),
                )
                result: dict[str, Any] = run_refiner_failure_cleanup_sweep_for_scope(
                    session=session,
                    settings=settings,
                    media_scope=media_scope,
                )
                result["job_id"] = ctx.id
                detail = json.dumps(result, separators=(",", ":"), ensure_ascii=True)[:10_000]
                record_refiner_failure_cleanup_sweep_completed(
                    session,
                    media_scope=media_scope,
                    detail=detail,
                )

    return _run

