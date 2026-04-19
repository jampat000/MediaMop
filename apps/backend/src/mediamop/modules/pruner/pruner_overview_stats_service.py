from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from mediamop.modules.pruner.pruner_job_kinds import PRUNER_CANDIDATE_REMOVAL_PREVIEW_JOB_KIND
from mediamop.modules.pruner.pruner_jobs_model import PrunerJob, PrunerJobStatus
from mediamop.modules.pruner.schemas_pruner_overview_stats import PrunerOverviewStatsOut
from mediamop.platform.activity import constants as C
from mediamop.platform.activity.models import ActivityEvent


def build_pruner_overview_stats(db: Session, *, window_days: int = 30) -> PrunerOverviewStatsOut:
    wd = max(1, int(window_days))
    since = datetime.now(timezone.utc) - timedelta(days=wd)

    apply_rows = db.execute(
        select(ActivityEvent.detail).where(
            ActivityEvent.event_type == C.PRUNER_APPLY_LIBRARY_REMOVAL_COMPLETED,
            ActivityEvent.created_at >= since,
        ),
    ).all()

    items_removed = 0
    items_skipped = 0
    apply_runs = len(apply_rows)
    for (detail_raw,) in apply_rows:
        if not detail_raw:
            continue
        try:
            obj = json.loads(str(detail_raw))
        except json.JSONDecodeError:
            continue
        if not isinstance(obj, dict):
            continue
        try:
            items_removed += int(obj.get("removed") or 0)
            items_skipped += int(obj.get("skipped") or 0)
        except (TypeError, ValueError):
            continue

    failed_applies = int(
        db.scalar(
            select(func.count())
            .select_from(ActivityEvent)
            .where(
                ActivityEvent.event_type == C.PRUNER_APPLY_LIBRARY_REMOVAL_FAILED,
                ActivityEvent.created_at >= since,
            ),
        )
        or 0,
    )

    preview_runs = int(
        db.scalar(
            select(func.count())
            .select_from(PrunerJob)
            .where(
                PrunerJob.job_kind == PRUNER_CANDIDATE_REMOVAL_PREVIEW_JOB_KIND,
                PrunerJob.status == PrunerJobStatus.COMPLETED.value,
                PrunerJob.updated_at >= since,
            ),
        )
        or 0,
    )

    return PrunerOverviewStatsOut(
        window_days=wd,
        items_removed=items_removed,
        items_skipped=items_skipped,
        apply_runs=apply_runs,
        preview_runs=preview_runs,
        failed_applies=failed_applies,
    )
