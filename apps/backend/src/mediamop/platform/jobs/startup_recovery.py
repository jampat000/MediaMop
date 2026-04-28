"""Crash recovery for durable module job queues."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from mediamop.modules.pruner.pruner_jobs_model import PrunerJob, PrunerJobStatus
from mediamop.modules.refiner.jobs_model import RefinerJob, RefinerJobStatus
from mediamop.modules.subber.subber_jobs_model import SubberJob, SubberJobStatus


@dataclass(frozen=True, slots=True)
class StartupJobRecoveryResult:
    refiner_requeued: int = 0
    refiner_failed: int = 0
    pruner_requeued: int = 0
    pruner_failed: int = 0
    subber_requeued: int = 0
    subber_failed: int = 0

    @property
    def total_recovered(self) -> int:
        return (
            self.refiner_requeued
            + self.refiner_failed
            + self.pruner_requeued
            + self.pruner_failed
            + self.subber_requeued
            + self.subber_failed
        )

    def as_log_dict(self) -> dict[str, int]:
        return {
            "refiner_requeued": self.refiner_requeued,
            "refiner_failed": self.refiner_failed,
            "pruner_requeued": self.pruner_requeued,
            "pruner_failed": self.pruner_failed,
            "subber_requeued": self.subber_requeued,
            "subber_failed": self.subber_failed,
        }


def recover_incomplete_jobs_after_startup(session: Session, *, now: datetime | None = None) -> StartupJobRecoveryResult:
    """Convert jobs leased by a previous crashed process into explicit recoverable states.

    Workers claim by lease, then perform side effects, then terminalize the row. If the process
    exits mid-handler, rows can remain ``leased`` until the old lease expires. Startup is a hard
    process boundary for this single-node app, so a leased row at startup belongs to a dead worker.
    Requeue it when attempts remain, or mark it failed when the lease already consumed the final
    attempt. This makes incomplete work visible immediately instead of silently waiting on stale
    lease timestamps.
    """

    when = now if now is not None else datetime.now(timezone.utc)
    rr, rf = _recover_table(
        session,
        model=RefinerJob,
        leased_status=RefinerJobStatus.LEASED.value,
        pending_status=RefinerJobStatus.PENDING.value,
        failed_status=RefinerJobStatus.FAILED.value,
        module_name="Refiner",
        now=when,
    )
    pr, pf = _recover_table(
        session,
        model=PrunerJob,
        leased_status=PrunerJobStatus.LEASED.value,
        pending_status=PrunerJobStatus.PENDING.value,
        failed_status=PrunerJobStatus.FAILED.value,
        module_name="Pruner",
        now=when,
    )
    sr, sf = _recover_table(
        session,
        model=SubberJob,
        leased_status=SubberJobStatus.LEASED.value,
        pending_status=SubberJobStatus.PENDING.value,
        failed_status=SubberJobStatus.FAILED.value,
        module_name="Subber",
        now=when,
    )
    return StartupJobRecoveryResult(
        refiner_requeued=rr,
        refiner_failed=rf,
        pruner_requeued=pr,
        pruner_failed=pf,
        subber_requeued=sr,
        subber_failed=sf,
    )


def _recover_table(
    session: Session,
    *,
    model: type[Any],
    leased_status: str,
    pending_status: str,
    failed_status: str,
    module_name: str,
    now: datetime,
) -> tuple[int, int]:
    requeued = 0
    failed = 0
    rows = list(session.scalars(select(model).where(model.status == leased_status)).all())
    for row in rows:
        attempts = int(row.attempt_count or 0)
        max_attempts = max(1, int(row.max_attempts or 1))
        row.lease_owner = None
        row.lease_expires_at = None
        if attempts >= max_attempts:
            row.status = failed_status
            row.last_error = (
                f"{module_name} job was interrupted by a MediaMop restart after its final attempt. "
                f"Recovered at {now.isoformat()} and marked failed so the operator can inspect it."
            )
            failed += 1
        else:
            row.status = pending_status
            row.last_error = (
                f"{module_name} job was interrupted by a MediaMop restart. "
                f"Recovered at {now.isoformat()} and queued for another safe attempt."
            )
            requeued += 1
    session.flush()
    return requeued, failed
