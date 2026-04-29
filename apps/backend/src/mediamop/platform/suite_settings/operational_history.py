"""User-controlled reset for operational history.

This deliberately does not run from session expiry, log retention, or startup cleanup.
Operational history backs dashboard/overview facts and must only reset when an
operator explicitly asks for it.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from mediamop.modules.pruner.pruner_jobs_model import PrunerJob, PrunerJobStatus
from mediamop.modules.refiner.jobs_model import RefinerJob, RefinerJobStatus
from mediamop.modules.subber.subber_jobs_model import SubberJob, SubberJobStatus
from mediamop.platform.activity.models import ActivityEvent


@dataclass(frozen=True)
class OperationalHistoryResetResult:
    activity_events_deleted: int
    refiner_jobs_deleted: int
    pruner_jobs_deleted: int
    subber_jobs_deleted: int

    @property
    def total_deleted(self) -> int:
        return (
            self.activity_events_deleted
            + self.refiner_jobs_deleted
            + self.pruner_jobs_deleted
            + self.subber_jobs_deleted
        )


def _count(session: Session, model, *criteria) -> int:
    stmt = select(func.count()).select_from(model)
    for item in criteria:
        stmt = stmt.where(item)
    return int(session.scalar(stmt) or 0)


def reset_operational_history(session: Session) -> OperationalHistoryResetResult:
    """Clear completed history while leaving queued/running work and configuration intact."""

    refiner_terminal = (
        RefinerJobStatus.COMPLETED.value,
        RefinerJobStatus.FAILED.value,
        RefinerJobStatus.HANDLER_OK_FINALIZE_FAILED.value,
        RefinerJobStatus.CANCELLED.value,
    )
    pruner_terminal = (
        PrunerJobStatus.COMPLETED.value,
        PrunerJobStatus.FAILED.value,
        PrunerJobStatus.HANDLER_OK_FINALIZE_FAILED.value,
    )
    subber_terminal = (
        SubberJobStatus.COMPLETED.value,
        SubberJobStatus.FAILED.value,
        SubberJobStatus.HANDLER_OK_FINALIZE_FAILED.value,
    )

    activity_count = _count(session, ActivityEvent)
    refiner_count = _count(session, RefinerJob, RefinerJob.status.in_(refiner_terminal))
    pruner_count = _count(session, PrunerJob, PrunerJob.status.in_(pruner_terminal))
    subber_count = _count(session, SubberJob, SubberJob.status.in_(subber_terminal))

    session.execute(delete(ActivityEvent))
    session.execute(delete(RefinerJob).where(RefinerJob.status.in_(refiner_terminal)))
    session.execute(delete(PrunerJob).where(PrunerJob.status.in_(pruner_terminal)))
    session.execute(delete(SubberJob).where(SubberJob.status.in_(subber_terminal)))

    return OperationalHistoryResetResult(
        activity_events_deleted=activity_count,
        refiner_jobs_deleted=refiner_count,
        pruner_jobs_deleted=pruner_count,
        subber_jobs_deleted=subber_count,
    )
