"""User-controlled reset for operational history.

This deliberately does not run from session expiry, log retention, or startup cleanup.
Operational history backs overview facts and must only reset when an
operator explicitly asks for it.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from weir.platform.activity.models import ActivityEvent
from weir.refiner.jobs_model import RefinerJob, RefinerJobStatus


@dataclass(frozen=True)
class OperationalHistoryResetResult:
    activity_events_deleted: int
    refiner_jobs_deleted: int

    @property
    def total_deleted(self) -> int:
        return self.activity_events_deleted + self.refiner_jobs_deleted


def _count(session: Session, model, *criteria) -> int:
    stmt = select(func.count()).select_from(model)
    for item in criteria:
        stmt = stmt.where(item)
    return int(session.scalar(stmt) or 0)


def reset_operational_history(session: Session) -> OperationalHistoryResetResult:
    """Clear completed history while leaving queued/running work and configuration intact.

    This also clears Refiner completed-output guard events. Locked source folders
    still visible to the scanner can be queued again on the next scan.
    """

    refiner_terminal = (
        RefinerJobStatus.COMPLETED.value,
        RefinerJobStatus.FAILED.value,
        RefinerJobStatus.HANDLER_OK_FINALIZE_FAILED.value,
        RefinerJobStatus.CANCELLED.value,
    )

    activity_count = _count(session, ActivityEvent)
    refiner_count = _count(session, RefinerJob, RefinerJob.status.in_(refiner_terminal))

    session.execute(delete(ActivityEvent))
    session.execute(delete(RefinerJob).where(RefinerJob.status.in_(refiner_terminal)))

    return OperationalHistoryResetResult(
        activity_events_deleted=activity_count,
        refiner_jobs_deleted=refiner_count,
    )


def preview_operational_history_reset(session: Session) -> OperationalHistoryResetResult:
    """What a reset would remove, counted the same way, without removing anything."""

    refiner_terminal = (
        RefinerJobStatus.COMPLETED.value,
        RefinerJobStatus.FAILED.value,
        RefinerJobStatus.HANDLER_OK_FINALIZE_FAILED.value,
        RefinerJobStatus.CANCELLED.value,
    )
    return OperationalHistoryResetResult(
        activity_events_deleted=_count(session, ActivityEvent),
        refiner_jobs_deleted=_count(session, RefinerJob, RefinerJob.status.in_(refiner_terminal)),
    )
