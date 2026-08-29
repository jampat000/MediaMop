"""Refiner HTTP: the maintenance job families — ``/api/v1/refiner/maintenance``.

Until #339 these families were switched on by an undocumented environment variable, and
even then there was **no way to run one from outside the process, by any means**. An
operator who wanted to reclaim stale work files had to wait for a timer they could not see.

Triggering by hand deliberately ignores the schedule toggle. The toggle says whether
MediaMop runs the family on its own; someone asking for it now has already decided.
"""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, HTTPException, Request
from sqlalchemy import select
from starlette import status as http_status

from mediamop.api.deps import DbSessionDep, SettingsDep
from mediamop.core.config import MediaMopSettings
from mediamop.modules.refiner.jobs_model import RefinerJob, RefinerJobStatus
from mediamop.modules.refiner.refiner_failure_cleanup_enqueue import enqueue_refiner_failure_cleanup_sweep_job
from mediamop.modules.refiner.refiner_failure_cleanup_job_kinds import (
    REFINER_MOVIE_FAILURE_CLEANUP_SWEEP_JOB_KIND,
    REFINER_TV_FAILURE_CLEANUP_SWEEP_JOB_KIND,
)
from mediamop.modules.refiner.refiner_operator_settings_service import ensure_refiner_operator_settings_row
from mediamop.modules.refiner.refiner_work_temp_stale_sweep_enqueue import (
    enqueue_refiner_work_temp_stale_sweep_job,
)
from mediamop.modules.refiner.refiner_work_temp_stale_sweep_job_kinds import (
    REFINER_WORK_TEMP_STALE_SWEEP_JOB_KIND,
)
from mediamop.modules.refiner.schemas_refiner_maintenance import (
    MaintenanceFamilyStateOut,
    MaintenanceStateOut,
    MaintenanceTriggerIn,
    MaintenanceTriggerOut,
)
from mediamop.platform.auth.authorization import RequireOperatorDep
from mediamop.platform.auth.csrf import (
    current_raw_session_token,
    require_session_secret,
    validate_browser_post_origin,
    verify_csrf_token,
)
from mediamop.platform.auth.deps_auth import UserPublicDep

router = APIRouter(tags=["refiner"])

_FAMILY_JOB_KINDS: dict[str, tuple[str, ...]] = {
    "work_temp_stale_sweep": (REFINER_WORK_TEMP_STALE_SWEEP_JOB_KIND,),
    "failure_cleanup": (
        REFINER_MOVIE_FAILURE_CLEANUP_SWEEP_JOB_KIND,
        REFINER_TV_FAILURE_CLEANUP_SWEEP_JOB_KIND,
    ),
}

_FAMILY_DESCRIPTIONS: dict[str, str] = {
    "work_temp_stale_sweep": ("Reclaims MediaMop's own stale working files. Safe, and switched on by default."),
    "failure_cleanup": (
        "Removes the source release folder after a file has failed terminally. This deletes the original, "
        "so it stays switched off until you choose it."
    ),
}


def _verify_csrf(request: Request, settings: MediaMopSettings, token: str) -> None:
    validate_browser_post_origin(request, settings)
    secret = require_session_secret(settings)
    if not verify_csrf_token(secret, token, raw_session_token=current_raw_session_token(request, settings)):
        raise HTTPException(status_code=http_status.HTTP_400_BAD_REQUEST, detail="Invalid or expired CSRF token.")


def _state_for(db: DbSessionDep, family: str, *, enabled: bool) -> MaintenanceFamilyStateOut:
    kinds = _FAMILY_JOB_KINDS[family]
    rows = list(db.scalars(select(RefinerJob).where(RefinerJob.job_kind.in_(kinds)).order_by(RefinerJob.id.desc())))
    pending = sum(1 for r in rows if r.status == RefinerJobStatus.PENDING.value)
    running = sum(1 for r in rows if r.status == RefinerJobStatus.LEASED.value)

    completed = next((r for r in rows if r.status == RefinerJobStatus.COMPLETED.value), None)
    failed = next((r for r in rows if r.status == RefinerJobStatus.FAILED.value), None)
    return MaintenanceFamilyStateOut(
        family=family,  # type: ignore[arg-type]
        enabled=enabled,
        description=_FAMILY_DESCRIPTIONS[family],
        pending=pending,
        running=running,
        last_completed_at=completed.updated_at if completed is not None else None,
        last_failed_at=failed.updated_at if failed is not None else None,
        last_error=failed.last_error if failed is not None else None,
    )


@router.get("/refiner/maintenance", response_model=MaintenanceStateOut)
def get_refiner_maintenance(_user: UserPublicDep, db: DbSessionDep) -> MaintenanceStateOut:
    """What each maintenance family is doing, and whether its schedule is on."""

    operator = ensure_refiner_operator_settings_row(db)
    families = [
        _state_for(db, "work_temp_stale_sweep", enabled=bool(operator.work_temp_stale_sweep_enabled)),
        _state_for(db, "failure_cleanup", enabled=bool(operator.failure_cleanup_enabled)),
    ]
    db.commit()
    return MaintenanceStateOut(families=families)


@router.post("/refiner/maintenance/run", response_model=MaintenanceTriggerOut)
def post_refiner_maintenance_run(
    request: Request,
    _operator: RequireOperatorDep,
    db: DbSessionDep,
    settings: SettingsDep,
    body: MaintenanceTriggerIn,
) -> MaintenanceTriggerOut:
    """Run one maintenance family now.

    Ignores the schedule toggle on purpose: the toggle decides whether MediaMop runs this
    on its own, and somebody asking for it now has already decided.
    """

    _verify_csrf(request, settings, body.csrf_token)

    if body.family == "work_temp_stale_sweep":
        enqueue_refiner_work_temp_stale_sweep_job(db, media_scope=body.media_scope)
        db.commit()
        return MaintenanceTriggerOut(
            queued=True,
            detail=(
                f"Queued a work file sweep for {'TV' if body.media_scope == 'tv' else 'Movies'}. "
                "It runs as soon as a worker is free."
            ),
        )

    job, inserted = enqueue_refiner_failure_cleanup_sweep_job(db, media_scope=body.media_scope)
    db.commit()
    if not inserted:
        # Already waiting or running. Saying so beats silently returning success for a
        # button press that did nothing.
        return MaintenanceTriggerOut(
            queued=False,
            job_id=int(job.id),
            detail="A failure cleanup for this scope is already waiting or running, so nothing new was queued.",
        )
    return MaintenanceTriggerOut(
        queued=True,
        job_id=int(job.id),
        detail=(
            f"Queued failure cleanup for {'TV' if body.media_scope == 'tv' else 'Movies'}. "
            "It runs as soon as a worker is free."
        ),
    )
