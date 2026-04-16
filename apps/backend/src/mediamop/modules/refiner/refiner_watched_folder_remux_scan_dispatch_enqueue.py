"""Enqueue ``refiner.watched_folder.remux_scan_dispatch.v1`` (manual HTTP + Refiner-local periodic timer)."""

from __future__ import annotations

import json
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from mediamop.core.config import MediaMopSettings
from mediamop.modules.refiner.jobs_model import RefinerJob, RefinerJobStatus
from mediamop.modules.refiner.jobs_ops import refiner_enqueue_or_get_job
from mediamop.modules.refiner.refiner_path_settings_service import ensure_refiner_path_settings_row
from mediamop.modules.refiner.refiner_watched_folder_remux_scan_dispatch_job_kinds import (
    REFINER_WATCHED_FOLDER_REMUX_SCAN_DISPATCH_JOB_KIND,
)


def _scan_job_media_scope(payload_json: str | None) -> str:
    """Payload ``media_scope`` for scan jobs; missing/legacy payloads are treated as Movies."""

    raw = (payload_json or "").strip()
    if not raw:
        return "movie"
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return "movie"
    if not isinstance(data, dict):
        return "movie"
    ms = data.get("media_scope", "movie")
    if isinstance(ms, str) and ms in ("movie", "tv"):
        return ms
    return "movie"


def refiner_watched_folder_remux_scan_dispatch_queue_has_active_scan(
    session: Session,
    *,
    media_scope: str,
) -> bool:
    """True when a pending/leased scan job exists for this Movies vs TV scope."""

    want = (media_scope or "movie").strip().lower()
    if want not in ("movie", "tv"):
        want = "movie"
    rows = session.scalars(
        select(RefinerJob).where(
            RefinerJob.job_kind == REFINER_WATCHED_FOLDER_REMUX_SCAN_DISPATCH_JOB_KIND,
            RefinerJob.status.in_(
                (
                    RefinerJobStatus.PENDING.value,
                    RefinerJobStatus.LEASED.value,
                ),
            ),
        ),
    ).all()
    for job in rows:
        if _scan_job_media_scope(job.payload_json) == want:
            return True
    return False


def validate_watched_folder_scan_dispatch_prerequisites(
    session: Session,
    *,
    enqueue_remux_jobs: bool,
    remux_dry_run: bool,
    media_scope: str = "movie",
) -> tuple[bool, str | None]:
    """Shared checks for manual HTTP and periodic enqueue (path row; watched; live remux output)."""

    row = ensure_refiner_path_settings_row(session)
    scope = (media_scope or "movie").strip().lower()
    if scope == "tv":
        if not (row.refiner_tv_watched_folder or "").strip():
            return False, "no_saved_watched_folder"
        if enqueue_remux_jobs and not remux_dry_run and not (row.refiner_tv_output_folder or "").strip():
            return False, "missing_output_for_live_remux"
        return True, None
    if not (row.refiner_watched_folder or "").strip():
        return False, "no_saved_watched_folder"
    if enqueue_remux_jobs and not remux_dry_run and not (row.refiner_output_folder or "").strip():
        return False, "missing_output_for_live_remux"
    return True, None


def enqueue_watched_folder_remux_scan_dispatch_job(
    session: Session,
    *,
    enqueue_remux_jobs: bool,
    remux_dry_run: bool,
    scan_trigger: str,
    media_scope: str = "movie",
) -> RefinerJob:
    """Insert one scan job (unique ``dedupe_key``). Caller must commit."""

    payload = {
        "enqueue_remux_jobs": enqueue_remux_jobs,
        "remux_dry_run": remux_dry_run,
        "scan_trigger": scan_trigger,
        "media_scope": (media_scope or "movie").strip().lower(),
    }
    dedupe_key = f"{REFINER_WATCHED_FOLDER_REMUX_SCAN_DISPATCH_JOB_KIND}:{uuid4().hex}"
    return refiner_enqueue_or_get_job(
        session,
        dedupe_key=dedupe_key,
        job_kind=REFINER_WATCHED_FOLDER_REMUX_SCAN_DISPATCH_JOB_KIND,
        payload_json=json.dumps(payload, separators=(",", ":")),
    )


def try_enqueue_periodic_watched_folder_remux_scan_dispatch(
    session: Session,
    settings: MediaMopSettings,
    *,
    media_scope: str | None = None,
) -> tuple[bool, str | None]:
    """Periodic tick enqueue helper.

    When ``media_scope`` is provided, evaluates one scope only (Movies or TV). When omitted, preserves the original
    behavior and evaluates both scopes.
    """
    if media_scope is None:
        if not settings.refiner_watched_folder_remux_scan_dispatch_schedule_enabled:
            return False, "schedule_disabled"
        inserted_any = False
        last_skip: str | None = None
        for scope_name in ("movie", "tv"):
            inserted, skip = try_enqueue_periodic_watched_folder_remux_scan_dispatch(
                session,
                settings,
                media_scope=scope_name,
            )
            if inserted:
                inserted_any = True
            elif skip:
                last_skip = skip
        if inserted_any:
            return True, None
        return False, last_skip

    scope = (media_scope or "movie").strip().lower()
    if scope not in ("movie", "tv"):
        scope = "movie"
    if refiner_watched_folder_remux_scan_dispatch_queue_has_active_scan(session, media_scope=scope):
        return False, f"active_scan_already_queued_{scope}"
    ok, err = validate_watched_folder_scan_dispatch_prerequisites(
        session,
        enqueue_remux_jobs=settings.refiner_watched_folder_remux_scan_dispatch_periodic_enqueue_remux_jobs,
        remux_dry_run=settings.refiner_watched_folder_remux_scan_dispatch_periodic_remux_dry_run,
        media_scope=scope,
    )
    if not ok:
        return False, err
    enqueue_watched_folder_remux_scan_dispatch_job(
        session,
        enqueue_remux_jobs=settings.refiner_watched_folder_remux_scan_dispatch_periodic_enqueue_remux_jobs,
        remux_dry_run=settings.refiner_watched_folder_remux_scan_dispatch_periodic_remux_dry_run,
        scan_trigger="periodic",
        media_scope=scope,
    )
    return True, None
