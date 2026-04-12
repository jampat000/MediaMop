"""In-process Refiner worker handler for ``refiner.candidate_gate.v1`` (live queue + domain)."""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any, Literal

from sqlalchemy.orm import Session, sessionmaker

from mediamop.core.config import MediaMopSettings
from mediamop.modules.refiner.refiner_candidate_gate_activity import record_refiner_candidate_gate_completed
from mediamop.modules.refiner.refiner_candidate_gate_evaluate import evaluate_refiner_candidate_gate_from_queue_rows
from mediamop.modules.refiner.refiner_candidate_gate_queue_fetch import fetch_arr_v3_queue_rows
from mediamop.modules.refiner.worker_loop import RefinerJobWorkContext


def _parse_job_payload(payload_json: str | None) -> dict[str, Any]:
    if not payload_json or not payload_json.strip():
        msg = "candidate gate job requires payload_json with target and release_title"
        raise ValueError(msg)
    data = json.loads(payload_json)
    if not isinstance(data, dict):
        msg = "candidate gate payload must be a JSON object"
        raise ValueError(msg)
    return data


def make_refiner_candidate_gate_handler(
    settings: MediaMopSettings,
    session_factory: sessionmaker[Session],
) -> Callable[[RefinerJobWorkContext], None]:
    """Fetch live Radarr or Sonarr queue, map rows, evaluate ownership / upstream blocking."""

    def _run(ctx: RefinerJobWorkContext) -> None:
        body = _parse_job_payload(ctx.payload_json)
        target = body.get("target")
        if target not in ("radarr", "sonarr"):
            msg = "candidate gate payload.target must be 'radarr' or 'sonarr'"
            raise ValueError(msg)
        app: Literal["radarr", "sonarr"] = target
        title = body.get("release_title")
        if not isinstance(title, str) or not title.strip():
            msg = "candidate gate payload.release_title is required"
            raise ValueError(msg)
        year_raw = body.get("release_year")
        year: int | None
        if year_raw is None:
            year = None
        elif isinstance(year_raw, int):
            year = year_raw
        elif isinstance(year_raw, float) and year_raw.is_integer():
            year = int(year_raw)
        else:
            msg = "candidate gate payload.release_year must be an integer or null"
            raise ValueError(msg)

        output_path = body.get("output_path") if isinstance(body.get("output_path"), str) else None
        movie_id = body.get("movie_id")
        mid = int(movie_id) if isinstance(movie_id, int) else None
        series_id = body.get("series_id")
        sid = int(series_id) if isinstance(series_id, int) else None

        if app == "radarr":
            base, key = settings.arr_http_radarr_credentials()
        else:
            base, key = settings.arr_http_sonarr_credentials()
        if not base or not key:
            raise RuntimeError(
                "Refiner candidate gate needs Radarr/Sonarr URL and API key: set "
                "MEDIAMOP_ARR_*_BASE_URL and MEDIAMOP_ARR_*_API_KEY, or the legacy "
                "MEDIAMOP_FETCHER_* equivalents for the same app.",
            )

        rows = fetch_arr_v3_queue_rows(base_url=base, api_key=key, app=app)
        outcome = evaluate_refiner_candidate_gate_from_queue_rows(
            target=app,
            queue_rows=rows,
            release_title=title.strip(),
            release_year=year,
            output_path=output_path.strip() if output_path and output_path.strip() else None,
            movie_id=mid,
            series_id=sid,
        )
        detail_obj: dict[str, object] = {
            "job_id": ctx.id,
            "verdict": outcome.verdict,
            "owned": outcome.owned,
            "blocked_upstream": outcome.blocked_upstream,
            "queue_row_count": outcome.queue_row_count,
            "target": outcome.target,
            "reasons": list(outcome.reasons),
        }
        detail = json.dumps(detail_obj, separators=(",", ":"))[:10_000]
        with session_factory() as session:
            with session.begin():
                record_refiner_candidate_gate_completed(session, detail=detail)

    return _run
