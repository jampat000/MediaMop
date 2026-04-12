"""Read-only listing of persisted ``fetcher_jobs`` rows (module-wide Fetcher lane inspection)."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from mediamop.modules.fetcher.fetcher_jobs_model import FetcherJob, FetcherJobStatus
from mediamop.modules.fetcher.schemas_fetcher_jobs_inspection import (
    FetcherJobInspectionRow,
    FetcherJobsInspectionOut,
)

DEFAULT_TERMINAL_STATUSES: tuple[str, ...] = (
    FetcherJobStatus.COMPLETED.value,
    FetcherJobStatus.FAILED.value,
    FetcherJobStatus.HANDLER_OK_FINALIZE_FAILED.value,
)
_ALLOWED_STATUS: frozenset[str] = frozenset(s.value for s in FetcherJobStatus)


def validate_inspection_statuses(statuses: tuple[str, ...]) -> tuple[str, ...]:
    """Validate user-supplied status strings against persisted enum values."""

    unknown = [s for s in statuses if s not in _ALLOWED_STATUS]
    if unknown:
        msg = f"Invalid status filter values: {unknown!r}; allowed={sorted(_ALLOWED_STATUS)}"
        raise ValueError(msg)
    return statuses


def list_fetcher_jobs_for_inspection(
    session: Session,
    *,
    limit: int,
    statuses: tuple[str, ...],
    default_terminal_only: bool,
) -> FetcherJobsInspectionOut:
    """Return up to ``limit`` rows matching ``statuses``, ``updated_at`` descending."""

    stmt = select(FetcherJob).where(FetcherJob.status.in_(statuses)).order_by(FetcherJob.updated_at.desc()).limit(limit)
    rows = session.scalars(stmt).all()
    return FetcherJobsInspectionOut(
        jobs=[FetcherJobInspectionRow.model_validate(r) for r in rows],
        default_terminal_only=default_terminal_only,
    )
