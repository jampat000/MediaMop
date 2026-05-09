from __future__ import annotations

from sqlalchemy import delete

from mediamop.core.config import MediaMopSettings
from mediamop.core.db import create_db_engine, create_session_factory
from mediamop.modules.subber.subber_jobs_model import SubberJob, SubberJobStatus
from mediamop.modules.subber.subber_jobs_ops import _record_subber_queue_depth
from mediamop.platform.metrics.service import build_runtime_metrics_summary, reset_runtime_metrics_for_tests


def test_subber_queue_depth_metric_counts_pending_plus_leased_only() -> None:
    reset_runtime_metrics_for_tests()
    settings = MediaMopSettings.load()
    session_factory = create_session_factory(create_db_engine(settings))

    with session_factory() as session:
        session.execute(delete(SubberJob))
        session.add_all(
            [
                SubberJob(dedupe_key="depth-pending", job_kind="subber.search", status=SubberJobStatus.PENDING.value),
                SubberJob(dedupe_key="depth-leased", job_kind="subber.search", status=SubberJobStatus.LEASED.value),
                SubberJob(
                    dedupe_key="depth-completed",
                    job_kind="subber.search",
                    status=SubberJobStatus.COMPLETED.value,
                ),
                SubberJob(dedupe_key="depth-failed", job_kind="subber.search", status=SubberJobStatus.FAILED.value),
            ]
        )
        session.commit()

    with session_factory() as session:
        _record_subber_queue_depth(session)

    metrics = build_runtime_metrics_summary()
    assert metrics["module_queue_depths"].get("subber") == 2
