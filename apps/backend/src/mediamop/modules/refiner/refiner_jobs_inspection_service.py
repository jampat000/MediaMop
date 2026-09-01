"""Read-only ``refiner_jobs`` listing for operators (Refiner lane; not a cross-module framework)."""

from __future__ import annotations

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from mediamop.modules.refiner.jobs_model import RefinerJob, RefinerJobStatus
from mediamop.modules.refiner.refiner_watched_folder_remux_scan_dispatch_job_kinds import (
    REFINER_WATCHED_FOLDER_REMUX_SCAN_DISPATCH_JOB_KIND,
)
from mediamop.modules.refiner.schemas_refiner_jobs_inspection import (
    RefinerJobInspectionRow,
    RefinerJobsInspectionOut,
)
from mediamop.platform.jobs.operator_job_status import build_job_operator_status

_ALLOWED_STATUS: frozenset[str] = frozenset(s.value for s in RefinerJobStatus)


def validate_refiner_inspection_statuses(statuses: tuple[str, ...]) -> tuple[str, ...]:
    """Validate user-supplied status strings against persisted enum values."""

    unknown = [s for s in statuses if s not in _ALLOWED_STATUS]
    if unknown:
        msg = f"Invalid status filter values: {unknown!r}; allowed={sorted(_ALLOWED_STATUS)}"
        raise ValueError(msg)
    return statuses


def list_refiner_jobs_for_inspection(
    session: Session,
    *,
    limit: int,
    statuses: tuple[str, ...] | None,
) -> RefinerJobsInspectionOut:
    """Return up to ``limit`` rows, ``updated_at`` descending.

    When ``statuses`` is empty/None, returns the most recently touched rows **across all
    statuses** (Refiner queue is expected to stay small; operators need pending/leased visibility
    without repeating ``status=`` for every state).
    """

    if statuses:
        stmt = (
            select(RefinerJob)
            .where(RefinerJob.status.in_(statuses))
            .order_by(RefinerJob.updated_at.desc())
            .limit(limit)
        )
        default_recent_slice = False
    else:
        # Successful periodic folder checks happen frequently and can otherwise fill the
        # entire recent slice, hiding real file work and anything that needs attention.
        # They remain available in the explicit Completed view for diagnostics.
        stmt = (
            select(RefinerJob)
            .where(
                or_(
                    RefinerJob.status != RefinerJobStatus.COMPLETED.value,
                    RefinerJob.job_kind != REFINER_WATCHED_FOLDER_REMUX_SCAN_DISPATCH_JOB_KIND,
                )
            )
            .order_by(RefinerJob.updated_at.desc())
            .limit(limit)
        )
        default_recent_slice = True
    rows = session.scalars(stmt).all()
    inspection_rows = []
    for row in rows:
        item = RefinerJobInspectionRow.model_validate(row)
        operator_status = build_job_operator_status(
            module="refiner",
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
    return RefinerJobsInspectionOut(
        jobs=inspection_rows,
        default_recent_slice=default_recent_slice,
    )
