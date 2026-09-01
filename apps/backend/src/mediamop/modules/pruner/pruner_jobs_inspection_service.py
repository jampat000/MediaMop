"""Read-only ``pruner_jobs`` listing for operators."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from mediamop.modules.pruner.pruner_jobs_model import PrunerJob, PrunerJobStatus
from mediamop.modules.pruner.pruner_schemas import PrunerJobsInspectionOut, PrunerJobsInspectionRow
from mediamop.platform.jobs.operator_job_status import build_job_operator_status

_ALLOWED_STATUS: frozenset[str] = frozenset(s.value for s in PrunerJobStatus)


def validate_pruner_inspection_statuses(statuses: tuple[str, ...]) -> tuple[str, ...]:
    unknown = [s for s in statuses if s not in _ALLOWED_STATUS]
    if unknown:
        msg = f"Invalid status filter values: {unknown!r}; allowed={sorted(_ALLOWED_STATUS)}"
        raise ValueError(msg)
    return statuses


def list_pruner_jobs_for_inspection(
    session: Session,
    *,
    limit: int,
    statuses: tuple[str, ...] | None,
) -> PrunerJobsInspectionOut:
    if statuses:
        stmt = (
            select(PrunerJob).where(PrunerJob.status.in_(statuses)).order_by(PrunerJob.updated_at.desc()).limit(limit)
        )
        default_recent_slice = False
    else:
        stmt = select(PrunerJob).order_by(PrunerJob.updated_at.desc()).limit(limit)
        default_recent_slice = True
    rows = session.scalars(stmt).all()
    inspection_rows = []
    for row in rows:
        item = PrunerJobsInspectionRow.model_validate(row)
        operator_status = build_job_operator_status(
            module="pruner",
            job_kind=row.job_kind,
            status=row.status,
            last_error=row.last_error,
            payload_json=row.payload_json,
        )
        inspection_rows.append(
            item.model_copy(
                update={
                    "operator_message": operator_status.operator_message,
                    "next_action": operator_status.next_action,
                    "technical_detail": operator_status.technical_detail,
                }
            )
        )
    return PrunerJobsInspectionOut(
        jobs=inspection_rows,
        default_recent_slice=default_recent_slice,
    )
