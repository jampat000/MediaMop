"""Fetcher failed-import rows in Activity (module=fetcher, persisted from drive handlers)."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
from unittest.mock import patch

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from mediamop.core.config import MediaMopSettings
from mediamop.core.db import Base
from mediamop.modules.fetcher.failed_import_queue_job_handlers import build_failed_import_queue_job_handlers
from mediamop.modules.refiner.jobs_model import RefinerJob, RefinerJobStatus
from mediamop.modules.fetcher.radarr_cleanup_execution import RadarrFailedImportCleanupExecutionOutcome
from mediamop.modules.fetcher.radarr_failed_import_cleanup_drive import RadarrFailedImportCleanupDriveItemResult
from mediamop.modules.fetcher.radarr_failed_import_cleanup_job import enqueue_radarr_failed_import_cleanup_drive_job
from mediamop.modules.refiner.worker_loop import process_one_refiner_job
from mediamop.platform.activity import constants as act_c
from mediamop.platform.activity.models import ActivityEvent

import mediamop.modules.refiner.jobs_model  # noqa: F401
import mediamop.platform.activity.models  # noqa: F401
import mediamop.platform.auth.models  # noqa: F401


@pytest.fixture
def jobs_engine(tmp_path):
    from sqlalchemy import create_engine

    url = f"sqlite:///{tmp_path / 'fetcher_fi_activity.sqlite'}"
    engine = create_engine(
        url,
        connect_args={"check_same_thread": False, "timeout": 30.0},
        future=True,
    )
    Base.metadata.create_all(engine)
    return engine


@pytest.fixture
def session_factory(jobs_engine):
    return sessionmaker(
        bind=jobs_engine,
        class_=Session,
        autoflush=False,
        autocommit=False,
        expire_on_commit=False,
        future=True,
    )


def test_radarr_drive_removal_summary_activity(
    session_factory,
    failed_import_queue_worker_runtime_bundle,
) -> None:
    t0 = datetime(2026, 4, 10, 12, 0, 0, tzinfo=timezone.utc)
    settings = replace(
        MediaMopSettings.load(),
        refiner_radarr_base_url="http://127.0.0.1:7878",
        refiner_radarr_api_key="k",
    )
    fake_results = (
        RadarrFailedImportCleanupDriveItemResult(1, "m", RadarrFailedImportCleanupExecutionOutcome.REMOVED_QUEUE_ITEM),
        RadarrFailedImportCleanupDriveItemResult(2, "m2", RadarrFailedImportCleanupExecutionOutcome.NO_OP),
    )
    with session_factory() as s:
        enqueue_radarr_failed_import_cleanup_drive_job(s)
        s.commit()

    handlers = build_failed_import_queue_job_handlers(
        settings,
        session_factory,
        failed_import_runtime=failed_import_queue_worker_runtime_bundle,
    )
    with patch(
        "mediamop.modules.fetcher.radarr_failed_import_cleanup_job.drive_radarr_failed_import_cleanup_from_live_queue",
        return_value=fake_results,
    ):
        out = process_one_refiner_job(
            session_factory,
            lease_owner="unit",
            job_handlers=handlers,
            now=t0,
            lease_seconds=3600,
        )
    assert out == "processed"

    with session_factory() as s:
        assert s.get(RefinerJob, 1).status == RefinerJobStatus.COMPLETED.value
        rows = s.scalars(select(ActivityEvent).order_by(ActivityEvent.id.asc())).all()
        types = [r.event_type for r in rows]
        assert act_c.FETCHER_FAILED_IMPORT_RUN_STARTED in types
        assert act_c.FETCHER_FAILED_IMPORT_RUN_SUMMARY in types
        summary_ev = next(r for r in rows if r.event_type == act_c.FETCHER_FAILED_IMPORT_RUN_SUMMARY)
        assert summary_ev.module == "fetcher"
        assert "removed 1 eligible" in summary_ev.title.lower()
        assert summary_ev.detail is not None
        assert "not eligible" in summary_ev.detail.lower()


def test_radarr_drive_all_policy_skips_activity(
    session_factory,
    failed_import_queue_worker_runtime_bundle,
) -> None:
    t0 = datetime(2026, 4, 10, 12, 0, 0, tzinfo=timezone.utc)
    settings = replace(
        MediaMopSettings.load(),
        refiner_radarr_base_url="http://127.0.0.1:7878",
        refiner_radarr_api_key="k",
    )
    fake_results = tuple(
        RadarrFailedImportCleanupDriveItemResult(i, "b", RadarrFailedImportCleanupExecutionOutcome.NO_OP)
        for i in range(3)
    )
    with session_factory() as s:
        enqueue_radarr_failed_import_cleanup_drive_job(s)
        s.commit()

    handlers = build_failed_import_queue_job_handlers(
        settings,
        session_factory,
        failed_import_runtime=failed_import_queue_worker_runtime_bundle,
    )
    with patch(
        "mediamop.modules.fetcher.radarr_failed_import_cleanup_job.drive_radarr_failed_import_cleanup_from_live_queue",
        return_value=fake_results,
    ):
        process_one_refiner_job(
            session_factory,
            lease_owner="unit",
            job_handlers=handlers,
            now=t0,
            lease_seconds=3600,
        )

    with session_factory() as s:
        rows = s.scalars(select(ActivityEvent).order_by(ActivityEvent.id.asc())).all()
        types = [r.event_type for r in rows]
        assert act_c.FETCHER_FAILED_IMPORT_RUN_STARTED in types
        summary_ev = next(r for r in rows if r.event_type == act_c.FETCHER_FAILED_IMPORT_RUN_SUMMARY)
        assert summary_ev.module == "fetcher"
        assert "reviewed 3" in summary_ev.title.lower()
        assert "did not remove" in summary_ev.title.lower()
