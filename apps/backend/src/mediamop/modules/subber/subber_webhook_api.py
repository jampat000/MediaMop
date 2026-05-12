"""Radarr/Sonarr webhooks — validated by shared secret when MEDIAMOP_SUBBER_WEBHOOK_SECRET is set."""

from __future__ import annotations

import json
import secrets
import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Body, Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from mediamop.api.deps import DbSessionDep, SettingsDep
from mediamop.modules.subber.subber_job_kinds import SUBBER_JOB_KIND_WEBHOOK_IMPORT_MOVIES, SUBBER_JOB_KIND_WEBHOOK_IMPORT_TV
from mediamop.modules.subber.subber_jobs_ops import subber_enqueue_or_get_job

router = APIRouter(tags=["subber-webhooks"])


def _validate_webhook_secret(
    settings: SettingsDep,
    x_webhook_secret: Annotated[str | None, Header(alias="X-Webhook-Secret")] = None,
) -> None:
    """Reject requests when a webhook secret is configured and the header does not match."""
    configured = settings.subber_webhook_secret
    if not configured:
        return
    provided = (x_webhook_secret or "").strip()
    if not provided or not secrets.compare_digest(provided, configured):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing X-Webhook-Secret header.",
        )


def _enqueue_import(
    session: Session,
    *,
    job_kind: str,
    payload: dict[str, Any],
) -> None:
    dedupe = f"subber:wh:{job_kind}:{uuid.uuid4()}"
    subber_enqueue_or_get_job(
        session,
        dedupe_key=dedupe,
        job_kind=job_kind,
        payload_json=json.dumps(payload, separators=(",", ":")),
    )


@router.post("/webhook/sonarr", dependencies=[Depends(_validate_webhook_secret)])
def post_sonarr_webhook(
    db: DbSessionDep,
    payload: Annotated[dict[str, Any], Body(...)],
) -> dict[str, str]:
    if str(payload.get("eventType") or "").strip() != "Download":
        return {"status": "ignored"}
    eps = payload.get("episodes")
    if not isinstance(eps, list) or not eps:
        return {"status": "ignored"}
    ep0 = eps[0]
    if not isinstance(ep0, dict):
        return {"status": "ignored"}
    series = payload.get("series")
    series_title = str(series.get("title") or "").strip() if isinstance(series, dict) else ""
    ef = payload.get("episodeFile")
    path = str(ef.get("path") or "").strip() if isinstance(ef, dict) else ""
    if not path:
        return {"status": "ignored"}
    job_payload = {
        "file_path": path,
        "media_scope": "tv",
        "title": series_title,
        "year": None,
        "show_title": series_title or None,
        "season_number": ep0.get("seasonNumber"),
        "episode_number": ep0.get("episodeNumber"),
        "episode_title": ep0.get("title"),
        "sonarr_episode_id": ep0.get("id"),
        "radarr_movie_id": None,
    }
    _enqueue_import(db, job_kind=SUBBER_JOB_KIND_WEBHOOK_IMPORT_TV, payload=job_payload)
    return {"status": "ok"}


@router.post("/webhook/radarr", dependencies=[Depends(_validate_webhook_secret)])
def post_radarr_webhook(
    db: DbSessionDep,
    payload: Annotated[dict[str, Any], Body(...)],
) -> dict[str, str]:
    if str(payload.get("eventType") or "").strip() != "Download":
        return {"status": "ignored"}
    movie = payload.get("movie")
    if not isinstance(movie, dict):
        return {"status": "ignored"}
    mf = payload.get("movieFile")
    path = str(mf.get("path") or "").strip() if isinstance(mf, dict) else ""
    if not path:
        return {"status": "ignored"}
    job_payload = {
        "file_path": path,
        "media_scope": "movies",
        "title": str(movie.get("title") or "").strip(),
        "year": movie.get("year"),
        "show_title": None,
        "season_number": None,
        "episode_number": None,
        "episode_title": None,
        "sonarr_episode_id": None,
        "radarr_movie_id": movie.get("id"),
    }
    _enqueue_import(db, job_kind=SUBBER_JOB_KIND_WEBHOOK_IMPORT_MOVIES, payload=job_payload)
    return {"status": "ok"}
