"""Read-only ``pruner_jobs`` listing for operators."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from mediamop.modules.pruner.pruner_jobs_model import PrunerJob, PrunerJobStatus
from mediamop.modules.pruner.pruner_schemas import PrunerJobsInspectionOut, PrunerJobsInspectionRow

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
    return PrunerJobsInspectionOut(
        jobs=[PrunerJobsInspectionRow.model_validate(r) for r in rows],
        default_recent_slice=default_recent_slice,
    )
