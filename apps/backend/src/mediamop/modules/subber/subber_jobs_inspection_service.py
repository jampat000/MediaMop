"""Read-only ``subber_jobs`` listing."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from mediamop.modules.subber.subber_job_kinds import (
    SUBBER_JOB_KIND_LIBRARY_SCAN_MOVIES,
    SUBBER_JOB_KIND_LIBRARY_SCAN_TV,
    SUBBER_JOB_KIND_SUBTITLE_SEARCH_MOVIES,
    SUBBER_JOB_KIND_SUBTITLE_SEARCH_TV,
    SUBBER_JOB_KIND_WEBHOOK_IMPORT_MOVIES,
    SUBBER_JOB_KIND_WEBHOOK_IMPORT_TV,
)
from mediamop.modules.subber.subber_jobs_model import SubberJob, SubberJobStatus
from mediamop.modules.subber.subber_schemas import SubberJobsInspectionOut, SubberJobsInspectionRow

_ALLOWED_STATUS: frozenset[str] = frozenset(s.value for s in SubberJobStatus)


def validate_subber_inspection_statuses(statuses: tuple[str, ...]) -> tuple[str, ...]:
    unknown = [s for s in statuses if s not in _ALLOWED_STATUS]
    if unknown:
        msg = f"Invalid status filter values: {unknown!r}; allowed={sorted(_ALLOWED_STATUS)}"
        raise ValueError(msg)
    return statuses


def list_subber_jobs_for_inspection(
    session: Session,
    *,
    limit: int,
    statuses: tuple[str, ...] | None,
) -> SubberJobsInspectionOut:
    if statuses:
        stmt = (
            select(SubberJob)
            .where(SubberJob.status.in_(statuses))
            .order_by(SubberJob.updated_at.desc())
            .limit(limit)
        )
        default_recent_slice = False
    else:
        stmt = select(SubberJob).order_by(SubberJob.updated_at.desc()).limit(limit)
        default_recent_slice = True
    rows = session.scalars(stmt).all()
    jobs = [
        SubberJobsInspectionRow(
            id=int(r.id),
            dedupe_key=str(r.dedupe_key),
            job_kind=str(r.job_kind),
            status=str(r.status),
            scope=infer_subber_job_scope(job_kind=str(r.job_kind), payload_json=r.payload_json),
            payload_json=r.payload_json,
            last_error=r.last_error,
            created_at=r.created_at,
            updated_at=r.updated_at,
        )
        for r in rows
    ]
    return SubberJobsInspectionOut(jobs=jobs, default_recent_slice=default_recent_slice)


def media_scope_from_payload(payload_json: str | None) -> str | None:
    if not payload_json:
        return None
    try:
        import json

        p = json.loads(payload_json)
        s = p.get("media_scope")
        return str(s) if s is not None else None
    except (json.JSONDecodeError, TypeError):
        return None


def infer_subber_job_scope(*, job_kind: str, payload_json: str | None) -> str | None:
    """Best-effort ``tv`` / ``movies`` for UI — payload ``media_scope`` or implied by ``job_kind``."""

    if job_kind in (
        SUBBER_JOB_KIND_SUBTITLE_SEARCH_TV,
        SUBBER_JOB_KIND_LIBRARY_SCAN_TV,
        SUBBER_JOB_KIND_WEBHOOK_IMPORT_TV,
    ):
        return "tv"
    if job_kind in (
        SUBBER_JOB_KIND_SUBTITLE_SEARCH_MOVIES,
        SUBBER_JOB_KIND_LIBRARY_SCAN_MOVIES,
        SUBBER_JOB_KIND_WEBHOOK_IMPORT_MOVIES,
    ):
        return "movies"
    return media_scope_from_payload(payload_json)
