"""Refiner Pass 15: Radarr live cleanup drive refiner_jobs producer + handler."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
from unittest.mock import patch

import pytest
from sqlalchemy.orm import Session, sessionmaker

from mediamop.core.config import MediaMopSettings
from mediamop.modules.refiner.job_handlers_registry import build_production_refiner_job_handlers
from mediamop.modules.refiner.jobs_model import RefinerJob, RefinerJobStatus
from mediamop.modules.refiner.radarr_failed_import_cleanup_job import (
    REFINER_JOB_KIND_RADARR_FAILED_IMPORT_CLEANUP_DRIVE,
    RADARR_FAILED_IMPORT_CLEANUP_DRIVE_DEDUPE_KEY,
    enqueue_radarr_failed_import_cleanup_drive_job,
)
from mediamop.modules.refiner.worker_loop import process_one_refiner_job

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
    assert a.job_kind == REFINER_JOB_KIND_RADARR_FAILED_IMPORT_CLEANUP_DRIVE
    assert a.dedupe_key == RADARR_FAILED_IMPORT_CLEANUP_DRIVE_DEDUPE_KEY


def test_build_production_registry_registers_radarr_kind() -> None:
    s = MediaMopSettings.load()
    reg = build_production_refiner_job_handlers(s)
    assert REFINER_JOB_KIND_RADARR_FAILED_IMPORT_CLEANUP_DRIVE in reg


def test_radarr_handler_calls_drive_when_radarr_configured(session_factory) -> None:
    t0 = datetime(2026, 4, 10, 12, 0, 0, tzinfo=timezone.utc)
    base = MediaMopSettings.load()
    settings = replace(
        base,
        refiner_radarr_base_url="http://127.0.0.1:7878",
        refiner_radarr_api_key="test-key",
    )
    with session_factory() as s:
        enqueue_radarr_failed_import_cleanup_drive_job(s)
        s.commit()

    handlers = build_production_refiner_job_handlers(settings)
    with patch(
        "mediamop.modules.refiner.radarr_failed_import_cleanup_job.drive_radarr_failed_import_cleanup_from_live_queue",
    ) as drive_mock:
        out = process_one_refiner_job(
            session_factory,
            lease_owner="unit",
            job_handlers=handlers,
            now=t0,
            lease_seconds=3600,
        )
    assert out == "processed"
    drive_mock.assert_called_once()
    _args, kwargs = drive_mock.call_args
    assert _args[0] is settings
    assert "queue_fetch_client" in kwargs and "queue_operations" in kwargs

    with session_factory() as s:
        row = s.get(RefinerJob, 1)
        assert row.status == RefinerJobStatus.COMPLETED.value


def test_radarr_handler_failure_requeues_via_fail_op(session_factory) -> None:
    t0 = datetime(2026, 4, 10, 12, 0, 0, tzinfo=timezone.utc)
    base = MediaMopSettings.load()
    settings = replace(
        base,
        refiner_radarr_base_url="http://127.0.0.1:7878",
        refiner_radarr_api_key="test-key",
    )
    with session_factory() as s:
        enqueue_radarr_failed_import_cleanup_drive_job(s)
        s.commit()

    handlers = build_production_refiner_job_handlers(settings)
    with patch(
        "mediamop.modules.refiner.radarr_failed_import_cleanup_job.drive_radarr_failed_import_cleanup_from_live_queue",
        side_effect=RuntimeError("radarr down"),
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
        row = s.get(RefinerJob, 1)
        assert row.status == RefinerJobStatus.PENDING.value
        assert "radarr down" in (row.last_error or "")


def test_radarr_handler_without_config_fails_job(session_factory) -> None:
    t0 = datetime(2026, 4, 10, 12, 0, 0, tzinfo=timezone.utc)
    base = MediaMopSettings.load()
    settings = replace(base, refiner_radarr_base_url=None, refiner_radarr_api_key=None)
    with session_factory() as s:
        enqueue_radarr_failed_import_cleanup_drive_job(s)
        s.commit()

    handlers = build_production_refiner_job_handlers(settings)
    out = process_one_refiner_job(
        session_factory,
        lease_owner="unit",
        job_handlers=handlers,
        now=t0,
        lease_seconds=3600,
    )
    assert out == "processed"
    with session_factory() as s:
        row = s.get(RefinerJob, 1)
        assert row.status == RefinerJobStatus.PENDING.value
        assert "MEDIAMOP_REFINER_RADARR" in (row.last_error or "")


def test_idle_with_production_handlers_and_no_jobs(session_factory) -> None:
    handlers = build_production_refiner_job_handlers(MediaMopSettings.load())
    out = process_one_refiner_job(
        session_factory,
        lease_owner="unit",
        job_handlers=handlers,
    )
    assert out == "idle"
