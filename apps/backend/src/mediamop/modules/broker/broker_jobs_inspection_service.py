"""Read-only ``broker_jobs`` listing."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from mediamop.modules.broker.broker_jobs_model import BrokerJob, BrokerJobStatus
from mediamop.modules.broker.broker_schemas import BrokerJobOut, BrokerJobsInspectionOut

_ALLOWED_STATUS: frozenset[str] = frozenset(s.value for s in BrokerJobStatus)


def validate_broker_inspection_statuses(statuses: tuple[str, ...]) -> tuple[str, ...]:
    unknown = [s for s in statuses if s not in _ALLOWED_STATUS]
    if unknown:
        msg = f"Invalid status filter values: {unknown!r}; allowed={sorted(_ALLOWED_STATUS)}"
        raise ValueError(msg)
    return statuses


def infer_broker_job_scope(*, job_kind: str) -> str | None:
    if "sonarr" in job_kind:
        return "sonarr"
    if "radarr" in job_kind:
        return "radarr"
    return None


def list_broker_jobs_for_inspection(
    session: Session,
    *,
    limit: int,
    statuses: tuple[str, ...] | None,
) -> BrokerJobsInspectionOut:
    if statuses:
        stmt = (
            select(BrokerJob)
            .where(BrokerJob.status.in_(statuses))
            .order_by(BrokerJob.updated_at.desc())
            .limit(limit)
        )
        default_recent_slice = False
    else:
        stmt = select(BrokerJob).order_by(BrokerJob.updated_at.desc()).limit(limit)
        default_recent_slice = True
    rows = session.scalars(stmt).all()
    jobs = [
        BrokerJobOut(
            id=int(r.id),
            dedupe_key=str(r.dedupe_key),
            job_kind=str(r.job_kind),
            status=str(r.status),
            attempt_count=int(r.attempt_count),
            scope=infer_broker_job_scope(job_kind=str(r.job_kind)),
            payload_json=r.payload_json,
            last_error=r.last_error,
            created_at=r.created_at,
            updated_at=r.updated_at,
        )
        for r in rows
    ]
    return BrokerJobsInspectionOut(jobs=jobs, default_recent_slice=default_recent_slice)
