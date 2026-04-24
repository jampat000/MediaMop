from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from mediamop.modules.refiner.jobs_model import RefinerJob, RefinerJobStatus
from mediamop.modules.refiner.refiner_file_remux_pass_job_kinds import REFINER_FILE_REMUX_PASS_JOB_KIND
from mediamop.modules.refiner.refiner_file_remux_pass_visibility import (
    REMUX_PASS_OUTCOME_LIVE_OUTPUT_WRITTEN,
    REMUX_PASS_OUTCOME_LIVE_SKIPPED_NOT_REQUIRED,
)
from mediamop.modules.refiner.schemas_refiner_overview_stats import RefinerOverviewStatsOut
from mediamop.platform.activity import constants as activity_constants
from mediamop.platform.activity.models import ActivityEvent


def _json_int(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        try:
            return int(float(text))
        except ValueError:
            return None
    return None


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

    remux_rows = db.execute(
        select(ActivityEvent.detail).where(
            ActivityEvent.event_type == activity_constants.REFINER_FILE_REMUX_PASS_COMPLETED,
            ActivityEvent.created_at >= since,
        ),
    ).all()

    output_written_count = 0
    already_optimized_count = 0
    total_source_bytes = 0
    total_output_bytes = 0
    for (detail_raw,) in remux_rows:
        if not detail_raw:
            continue
        try:
            payload = json.loads(str(detail_raw))
        except json.JSONDecodeError:
            continue
        if not isinstance(payload, dict):
            continue
        outcome = str(payload.get("outcome") or "").strip()
        if outcome == REMUX_PASS_OUTCOME_LIVE_OUTPUT_WRITTEN:
            output_written_count += 1
            source_bytes = _json_int(payload.get("source_size_bytes"))
            output_bytes = _json_int(payload.get("output_size_bytes"))
            if source_bytes is not None and output_bytes is not None:
                total_source_bytes += max(0, source_bytes)
                total_output_bytes += max(0, output_bytes)
        elif outcome == REMUX_PASS_OUTCOME_LIVE_SKIPPED_NOT_REQUIRED:
            already_optimized_count += 1

    net_space_saved_bytes = total_source_bytes - total_output_bytes
    net_space_saved_percent = round((net_space_saved_bytes / total_source_bytes) * 100.0, 1) if total_source_bytes > 0 else 0.0

    return RefinerOverviewStatsOut(
        window_days=max(1, int(window_days)),
        files_processed=completed,
        files_failed=failed,
        success_rate_percent=rate,
        output_written_count=output_written_count,
        already_optimized_count=already_optimized_count,
        net_space_saved_bytes=net_space_saved_bytes,
        net_space_saved_percent=net_space_saved_percent,
    )
