"""Enqueue ``refiner.watched_folder.remux_scan_dispatch.v1`` (manual HTTP + Refiner-local periodic timer)."""

from __future__ import annotations

import json
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from mediamop.core.config import MediaMopSettings
from mediamop.modules.refiner.jobs_model import RefinerJob, RefinerJobStatus
from mediamop.modules.refiner.jobs_ops import refiner_enqueue_or_get_job
from mediamop.modules.refiner.refiner_library_service import resolve_library
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


def _scan_job_library_id(payload_json: str | None) -> int | None:
    """Payload library id, or ``None`` for a pre-library/legacy scan job."""

    raw = (payload_json or "").strip()
    if not raw:
        return None
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None
    value = data.get("library_id")
    return int(value) if isinstance(value, int) and value > 0 else None


def refiner_watched_folder_remux_scan_dispatch_queue_has_active_scan(
    session: Session,
    *,
    media_scope: str,
    library_id: int | None = None,
) -> bool:
    """True when a pending/leased scan already covers this exact library.

    Legacy jobs have no library id and still occupy their whole Movies/TV scope. New
    jobs are library-specific, so two Movies libraries can be scanned independently.
    """

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
        job_library_id = _scan_job_library_id(job.payload_json)
        if library_id is not None:
            if job_library_id == int(library_id):
                return True
            if job_library_id is None and _scan_job_media_scope(job.payload_json) == want:
                return True
            continue
        if _scan_job_media_scope(job.payload_json) == want:
            return True
    return False


def validate_watched_folder_scan_dispatch_prerequisites(
    session: Session,
    *,
    enqueue_remux_jobs: bool,
    media_scope: str = "movie",
    library_id: int | None = None,
) -> tuple[bool, str | None]:
    """Shared checks for manual HTTP and periodic enqueue (library; watched; live remux output)."""

    library = resolve_library(session, library_id=library_id, media_scope=media_scope)
    if library is not None:
        if not (library.watched_folder or "").strip():
            return False, "no_saved_watched_folder"
        if enqueue_remux_jobs and not (library.output_folder or "").strip():
            return False, "missing_output_for_live_remux"
        return True, None

    # No library covers this scope, so there is nothing to scan. One store now (#363):
    # this is a database an operator emptied, not an unmigrated one.
    return False, "no_saved_watched_folder"


def enqueue_watched_folder_remux_scan_dispatch_job(
    session: Session,
    *,
    enqueue_remux_jobs: bool,
    scan_trigger: str,
    media_scope: str = "movie",
    library_id: int | None = None,
) -> RefinerJob:
    """Insert one scan job (unique ``dedupe_key``). Caller must commit."""

    payload: dict[str, object] = {
        "enqueue_remux_jobs": enqueue_remux_jobs,
        "scan_trigger": scan_trigger,
        "media_scope": (media_scope or "movie").strip().lower(),
    }
    if library_id is not None:
        payload["library_id"] = library_id
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
    library_id: int | None = None,
) -> tuple[bool, str | None]:
    """Periodic tick enqueue helper.

    When ``media_scope`` is provided, evaluates one scope only (Movies or TV) — this is the
    production call shape. When omitted, evaluates both scopes.

    Whether a scope is scheduled at all is decided by the caller from the per-scope
    ``movie_schedule_enabled`` / ``tv_schedule_enabled`` rows. There is deliberately no
    process-wide kill switch here: one existed, was only ever consulted on the
    ``media_scope is None`` path the scheduler never takes, and reported itself as live
    configuration while scheduled scans ran regardless (#329).
    """
    if media_scope is None and library_id is None:
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

    library = resolve_library(session, library_id=library_id, media_scope=media_scope)
    scope = ((library.media_scope if library is not None else media_scope) or "movie").strip().lower()
    if scope not in ("movie", "tv"):
        scope = "movie"
    resolved_library_id = int(library.id) if library is not None else library_id
    if refiner_watched_folder_remux_scan_dispatch_queue_has_active_scan(
        session,
        media_scope=scope,
        library_id=resolved_library_id,
    ):
        suffix = f"library_{resolved_library_id}" if resolved_library_id is not None else scope
        return False, f"active_scan_already_queued_{suffix}"
    ok, err = validate_watched_folder_scan_dispatch_prerequisites(
        session,
        enqueue_remux_jobs=settings.refiner_watched_folder_remux_scan_dispatch_periodic_enqueue_remux_jobs,
        media_scope=scope,
        library_id=resolved_library_id,
    )
    if not ok:
        return False, err
    enqueue_watched_folder_remux_scan_dispatch_job(
        session,
        enqueue_remux_jobs=settings.refiner_watched_folder_remux_scan_dispatch_periodic_enqueue_remux_jobs,
        scan_trigger="periodic",
        media_scope=scope,
        library_id=resolved_library_id,
    )
    return True, None
