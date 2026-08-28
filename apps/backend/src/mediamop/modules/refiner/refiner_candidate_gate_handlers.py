"""In-process Refiner worker handler for ``refiner.candidate_gate.v1`` (live managers + domain)."""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

from sqlalchemy.orm import Session, sessionmaker

from mediamop.core.config import MediaMopSettings
from mediamop.modules.refiner.refiner_candidate_gate_activity import record_refiner_candidate_gate_completed
from mediamop.modules.refiner.refiner_candidate_gate_evaluate import (
    evaluate_refiner_candidate_gate_from_manager_signals,
)
from mediamop.modules.refiner.worker_loop import RefinerJobWorkContext
from mediamop.platform.media_managers.manager_binding import collect_queue_signals
from mediamop.platform.media_managers.manager_port import MediaScope


def _parse_job_payload(payload_json: str | None) -> dict[str, Any]:
    if not payload_json or not payload_json.strip():
        msg = "candidate gate job requires payload_json with media_scope and release_title"
        raise ValueError(msg)
    data = json.loads(payload_json)
    if not isinstance(data, dict):
        msg = "candidate gate payload must be a JSON object"
        raise ValueError(msg)
    return data


def _optional_int(value: Any, *, field: str) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool):
        msg = f"candidate gate payload.{field} must be an integer or null"
        raise ValueError(msg)
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    msg = f"candidate gate payload.{field} must be an integer or null"
    raise ValueError(msg)


def make_refiner_candidate_gate_handler(
    settings: MediaMopSettings,
    session_factory: sessionmaker[Session],
) -> Callable[[RefinerJobWorkContext], None]:
    """Ask every manager covering the scope what it is importing, then evaluate ownership / blocking.

    A manager being unreachable does not fail the job. The gate reports what it could not
    ask, which is the whole reason it no longer reduces to one ``(url, key)`` pair.
    """

    def _run(ctx: RefinerJobWorkContext) -> None:
        body = _parse_job_payload(ctx.payload_json)
        raw_scope = body.get("media_scope")
        if raw_scope not in ("movie", "tv"):
            msg = "candidate gate payload.media_scope must be 'movie' or 'tv'"
            raise ValueError(msg)
        media_scope: MediaScope = raw_scope
        title = body.get("release_title")
        if not isinstance(title, str) or not title.strip():
            msg = "candidate gate payload.release_title is required"
            raise ValueError(msg)
        year = _optional_int(body.get("release_year"), field="release_year")
        entity_id = _optional_int(body.get("entity_id"), field="entity_id")
        raw_output_path = body.get("output_path")
        output_path = raw_output_path.strip() if isinstance(raw_output_path, str) and raw_output_path.strip() else None

        with session_factory() as session:
            signals = collect_queue_signals(session, settings, media_scope=media_scope)

        outcome = evaluate_refiner_candidate_gate_from_manager_signals(
            media_scope=media_scope,
            signals=signals,
            release_title=title.strip(),
            release_year=year,
            output_path=output_path,
            entity_id=entity_id,
        )
        detail_obj: dict[str, object] = {
            "job_id": ctx.id,
            "verdict": outcome.verdict,
            "owned": outcome.owned,
            "blocked_upstream": outcome.blocked_upstream,
            "queue_row_count": outcome.queue_row_count,
            "media_scope": outcome.media_scope,
            "managers_consulted": outcome.managers_consulted,
            "managers_reporting": outcome.managers_reporting,
            "managers_without_queue_signal": list(outcome.managers_without_queue_signal),
            "blocked_by_connection": outcome.blocked_by_connection,
            "reasons": list(outcome.reasons),
        }
        detail = json.dumps(detail_obj, separators=(",", ":"))[:10_000]
        with session_factory() as session, session.begin():
            record_refiner_candidate_gate_completed(session, detail=detail)

    return _run
