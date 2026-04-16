from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from mediamop.modules.refiner.jobs_model import RefinerJob, RefinerJobStatus
from mediamop.modules.refiner.refiner_file_remux_pass_job_kinds import REFINER_FILE_REMUX_PASS_JOB_KIND
from mediamop.modules.refiner.schemas_refiner_overview_stats import RefinerOverviewStatsOut


def build_refiner_overview_stats(db: Session, *, window_days: int = 30) -> RefinerOverviewStatsOut:
    since = datetime.now(timezone.utc) - timedelta(days=max(1, int(window_days)))
    completed = int(
        db.scalar(
            select(func.count())
            .select_from(RefinerJob)
            .where(
                RefinerJob.job_kind == REFINER_FILE_REMUX_PASS_JOB_KIND,
                RefinerJob.status == RefinerJobStatus.COMPLETED.value,
                RefinerJob.updated_at >= since,
            ),
        )
        or 0,
    )
    failed = int(
        db.scalar(
            select(func.count())
            .select_from(RefinerJob)
            .where(
                RefinerJob.job_kind == REFINER_FILE_REMUX_PASS_JOB_KIND,
                RefinerJob.status.in_(
                    (
                        RefinerJobStatus.FAILED.value,
                        RefinerJobStatus.HANDLER_OK_FINALIZE_FAILED.value,
                    ),
                ),
                RefinerJob.updated_at >= since,
            ),
        )
        or 0,
    )
    terminal = completed + failed
    rate = round((completed / terminal) * 100.0, 1) if terminal > 0 else 0.0
    return RefinerOverviewStatsOut(
        window_days=30,
        files_processed=completed,
        files_failed=failed,
        success_rate_percent=rate,
    )
