"""Read-only listing of persisted ``refiner_jobs`` rows for operator inspection."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from mediamop.modules.refiner.jobs_model import RefinerJob, RefinerJobStatus
from mediamop.modules.refiner.schemas_inspection import (
    RefinerJobInspectionRow,
    RefinerJobsInspectionOut,
)

DEFAULT_TERMINAL_STATUSES: tuple[str, ...] = (
    RefinerJobStatus.COMPLETED.value,
    RefinerJobStatus.FAILED.value,
    RefinerJobStatus.HANDLER_OK_FINALIZE_FAILED.value,
)

_ALLOWED_STATUS: frozenset[str] = frozenset(s.value for s in RefinerJobStatus)


def validate_inspection_statuses(statuses: tuple[str, ...]) -> tuple[str, ...]:
    """Return validated tuple or raise ValueError with the first invalid token."""

    for s in statuses:
        if s not in _ALLOWED_STATUS:
            raise ValueError(f"invalid refiner job status: {s!r}")
    return statuses


def list_refiner_jobs_for_inspection(
    session: Session,
    *,
    limit: int,
    statuses: tuple[str, ...],
    default_terminal_only: bool,
) -> RefinerJobsInspectionOut:
    stmt = (
        select(RefinerJob)
        .where(RefinerJob.status.in_(statuses))
        .order_by(RefinerJob.updated_at.desc())
        .limit(limit)
    )
    rows = session.scalars(stmt).all()
    return RefinerJobsInspectionOut(
        jobs=[RefinerJobInspectionRow.model_validate(r) for r in rows],
        default_terminal_only=default_terminal_only,
    )
