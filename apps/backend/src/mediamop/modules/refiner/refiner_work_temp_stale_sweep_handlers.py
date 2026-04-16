"""In-process Refiner worker handler for ``refiner.work_temp_stale_sweep.v1``."""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

from sqlalchemy.orm import Session, sessionmaker

from mediamop.core.config import MediaMopSettings
from mediamop.modules.refiner.refiner_temp_cleanup import (
    normalize_work_temp_sweep_media_scope,
    run_refiner_work_temp_stale_sweep_for_scope,
)
from mediamop.modules.refiner.refiner_work_temp_stale_sweep_activity import (
    record_refiner_work_temp_stale_sweep_completed,
)
from mediamop.modules.refiner.worker_loop import RefinerJobWorkContext


def _parse_work_temp_stale_sweep_payload(payload_json: str | None) -> str:
    if not payload_json or not payload_json.strip():
        msg = "work temp stale sweep payload is required (media_scope + optional dry_run)"
        raise ValueError(msg)
    data = json.loads(payload_json)
    if not isinstance(data, dict):
        msg = "work temp stale sweep payload must be a JSON object"
        raise ValueError(msg)
    raw_scope = data.get("media_scope")
    if raw_scope is None or not str(raw_scope).strip():
        msg = "work temp stale sweep payload must include media_scope (movie or tv)"
        raise ValueError(msg)
    media_scope = normalize_work_temp_sweep_media_scope(str(raw_scope))
    return media_scope


def make_refiner_work_temp_stale_sweep_handler(
    settings: MediaMopSettings,
    session_factory: sessionmaker[Session],
) -> Callable[[RefinerJobWorkContext], None]:
    """Remove (or preview removal of) stale Refiner temp files under one scope's saved work folder."""

    def _run(ctx: RefinerJobWorkContext) -> None:
        media_scope = _parse_work_temp_stale_sweep_payload(ctx.payload_json)
        with session_factory() as session:
            with session.begin():
                result: dict[str, Any] = run_refiner_work_temp_stale_sweep_for_scope(
                    session=session,
                    settings=settings,
                    media_scope=media_scope,
                )
                result["job_id"] = ctx.id
                detail = json.dumps(result, separators=(",", ":"), ensure_ascii=True)[:10_000]
                record_refiner_work_temp_stale_sweep_completed(
                    session,
                    media_scope=media_scope,
                    detail=detail,
                )

    return _run
