"""Radarr live cleanup drive fetcher_jobs producer + handler."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from mediamop.core.config import MediaMopSettings
from mediamop.platform.activity import constants as act_c
from mediamop.platform.activity.models import ActivityEvent
from mediamop.modules.fetcher.cleanup_policy_service import FailedImportDrivePolicySource
from mediamop.modules.fetcher.failed_import_queue_job_handlers import build_failed_import_queue_job_handlers
from mediamop.modules.fetcher.radarr_failed_import_cleanup_job import (
    FAILED_IMPORT_JOB_KIND_RADARR_CLEANUP_DRIVE,
    RADARR_FAILED_IMPORT_CLEANUP_DRIVE_DEDUPE_KEY,
    enqueue_radarr_failed_import_cleanup_drive_job,
)
from mediamop.modules.fetcher.fetcher_jobs_model import FetcherJob, FetcherJobStatus
from mediamop.modules.fetcher.fetcher_worker_loop import process_one_fetcher_job

import mediamop.modules.fetcher.fetcher_jobs_model  # noqa: F401
import mediamop.modules.refiner.jobs_model  # noqa: F401
import mediamop.platform.activity.models  # noqa: F401
import mediamop.platform.auth.models  # noqa: F401
from mediamop.core.db import Base


@pytest.fixture
def jobs_engine(tmp_path):
    from sqlalchemy import create_engine

    url = f"sqlite:///{tmp_path / 'radarr_job.sqlite'}"
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


def test_enqueue_radarr_cleanup_drive_job_dedupes(session_factory) -> None:
    with session_factory() as s:
        a = enqueue_radarr_failed_import_cleanup_drive_job(s)
        s.commit()
        aid = a.id
    with session_factory() as s:
        b = enqueue_radarr_failed_import_cleanup_drive_job(s)
        s.commit()
    assert b.id == aid
    assert a.job_kind == FAILED_IMPORT_JOB_KIND_RADARR_CLEANUP_DRIVE
    assert a.dedupe_key == RADARR_FAILED_IMPORT_CLEANUP_DRIVE_DEDUPE_KEY


def test_build_production_registry_registers_radarr_kind(failed_import_queue_worker_runtime_bundle) -> None:
    s = MediaMopSettings.load()
    reg = build_failed_import_queue_job_handlers(
        s,
        MagicMock(),
        failed_import_runtime=failed_import_queue_worker_runtime_bundle,
    )
    assert FAILED_IMPORT_JOB_KIND_RADARR_CLEANUP_DRIVE in reg


def test_radarr_handler_calls_drive_when_radarr_configured(
    session_factory,
    failed_import_queue_worker_runtime_bundle,
) -> None:
    t0 = datetime(2026, 4, 10, 12, 0, 0, tzinfo=timezone.utc)
    base = MediaMopSettings.load()
    settings = replace(
        base,
        fetcher_radarr_base_url="http://127.0.0.1:7878",
        fetcher_radarr_api_key="test-key",
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
    ) as drive_mock:
        drive_mock.return_value = ()
        out = process_one_fetcher_job(
            session_factory,
            lease_owner="unit",
            job_handlers=handlers,
            now=t0,
            lease_seconds=3600,
        )
    assert out == "processed"
    drive_mock.assert_called_once()
    _args, kwargs = drive_mock.call_args
    assert isinstance(_args[0], FailedImportDrivePolicySource)
    assert _args[0].bundle == settings.failed_import_cleanup_env
    assert "queue_fetch_client" in kwargs and "queue_operations" in kwargs

    with session_factory() as s:
        row = s.get(FetcherJob, 1)
        assert row.status == FetcherJobStatus.COMPLETED.value
        rows = s.scalars(
            select(ActivityEvent)
            .where(ActivityEvent.module == "fetcher")
            .order_by(ActivityEvent.id.asc()),
        ).all()
        types = [r.event_type for r in rows]
        assert act_c.FETCHER_FAILED_IMPORT_RUN_STARTED in types
        assert act_c.FETCHER_FAILED_IMPORT_RUN_SUMMARY in types
        summary_ev = next(r for r in rows if r.event_type == act_c.FETCHER_FAILED_IMPORT_RUN_SUMMARY)
        assert "movie" in summary_ev.title.lower()
        assert "no rows" in summary_ev.title.lower() or "radarr" in summary_ev.title.lower()


def test_radarr_handler_failure_requeues_via_fail_op(
    session_factory,
    failed_import_queue_worker_runtime_bundle,
) -> None:
    t0 = datetime(2026, 4, 10, 12, 0, 0, tzinfo=timezone.utc)
    base = MediaMopSettings.load()
    settings = replace(
        base,
        fetcher_radarr_base_url="http://127.0.0.1:7878",
        fetcher_radarr_api_key="test-key",
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
        side_effect=RuntimeError("radarr down"),
    ):
        out = process_one_fetcher_job(
            session_factory,
            lease_owner="unit",
            job_handlers=handlers,
            now=t0,
            lease_seconds=3600,
        )
    assert out == "processed"
    with session_factory() as s:
        row = s.get(FetcherJob, 1)
        assert row.status == FetcherJobStatus.PENDING.value
        assert "radarr down" in (row.last_error or "")
        types = [
            r.event_type
            for r in s.scalars(select(ActivityEvent).where(ActivityEvent.module == "fetcher")).all()
        ]
        assert act_c.FETCHER_FAILED_IMPORT_RUN_STARTED in types
        fail_ev = s.scalars(
            select(ActivityEvent).where(ActivityEvent.event_type == act_c.FETCHER_FAILED_IMPORT_RUN_FAILED),
        ).first()
        assert fail_ev is not None
        assert fail_ev.module == "fetcher"
        assert "radarr down" in (fail_ev.detail or "")


def test_radarr_handler_without_config_fails_job(
    session_factory,
    failed_import_queue_worker_runtime_bundle,
) -> None:
    t0 = datetime(2026, 4, 10, 12, 0, 0, tzinfo=timezone.utc)
    base = MediaMopSettings.load()
    settings = replace(base, fetcher_radarr_base_url=None, fetcher_radarr_api_key=None)
    with session_factory() as s:
        enqueue_radarr_failed_import_cleanup_drive_job(s)
        s.commit()

    handlers = build_failed_import_queue_job_handlers(
        settings,
        session_factory,
        failed_import_runtime=failed_import_queue_worker_runtime_bundle,
    )
    out = process_one_fetcher_job(
        session_factory,
        lease_owner="unit",
        job_handlers=handlers,
        now=t0,
        lease_seconds=3600,
    )
    assert out == "processed"
    with session_factory() as s:
        row = s.get(FetcherJob, 1)
        assert row.status == FetcherJobStatus.PENDING.value
        assert "MEDIAMOP_FETCHER_RADARR" in (row.last_error or "")
        rows = s.scalars(select(ActivityEvent).where(ActivityEvent.module == "fetcher")).all()
        types = [r.event_type for r in rows]
        assert act_c.FETCHER_FAILED_IMPORT_RUN_STARTED not in types
        fail_ev = s.scalars(
            select(ActivityEvent).where(ActivityEvent.event_type == act_c.FETCHER_FAILED_IMPORT_RUN_FAILED),
        ).first()
        assert fail_ev is not None
        assert fail_ev.module == "fetcher"


def test_idle_with_production_handlers_and_no_jobs(
    session_factory,
    failed_import_queue_worker_runtime_bundle,
) -> None:
    handlers = build_failed_import_queue_job_handlers(
        MediaMopSettings.load(),
        session_factory,
        failed_import_runtime=failed_import_queue_worker_runtime_bundle,
    )
    out = process_one_fetcher_job(
        session_factory,
        lease_owner="unit",
        job_handlers=handlers,
    )
    assert out == "idle"
