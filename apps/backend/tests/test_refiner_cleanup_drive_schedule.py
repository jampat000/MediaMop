"""Independent Radarr/Sonarr periodic cleanup-drive enqueue schedules."""

from __future__ import annotations

import asyncio
from dataclasses import replace

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from mediamop.core.config import MediaMopSettings
from mediamop.modules.refiner.jobs_model import RefinerJob
from mediamop.modules.refiner import periodic_cleanup_drive_enqueue as periodic_enqueue_mod
from mediamop.modules.fetcher.failed_import_cleanup_drive_schedule_specs import (
    failed_import_cleanup_drive_schedule_specs,
)
from mediamop.modules.fetcher.radarr_failed_import_cleanup_job import (
    FAILED_IMPORT_JOB_KIND_RADARR_CLEANUP_DRIVE,
    enqueue_radarr_failed_import_cleanup_drive_job,
)
from mediamop.modules.fetcher.sonarr_failed_import_cleanup_job import (
    FAILED_IMPORT_JOB_KIND_SONARR_CLEANUP_DRIVE,
    enqueue_sonarr_failed_import_cleanup_drive_job,
)
from mediamop.modules.refiner.failed_import_queue_worker_ports import NoOpFailedImportTimedSchedulePassQueuedPort
from mediamop.modules.refiner.periodic_cleanup_drive_enqueue import (
    run_periodic_refiner_cleanup_drive_enqueue,
    start_refiner_cleanup_drive_enqueue_schedule_tasks,
    stop_refiner_cleanup_drive_enqueue_schedule_tasks,
)
from mediamop.platform.activity import constants as act_c
from mediamop.platform.activity.models import ActivityEvent

import mediamop.modules.refiner.jobs_model  # noqa: F401
import mediamop.platform.activity.models  # noqa: F401
import mediamop.platform.auth.models  # noqa: F401
from mediamop.core.db import Base


@pytest.fixture
def jobs_engine(tmp_path):
    from sqlalchemy import create_engine

    url = f"sqlite:///{tmp_path / 'schedule.sqlite'}"
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


def _base_settings() -> MediaMopSettings:
    return MediaMopSettings.load()


def test_schedule_specs_radarr_only_when_radarr_enabled() -> None:
    base = _base_settings()
    s = replace(
        base,
        failed_import_radarr_cleanup_drive_schedule_enabled=True,
        failed_import_radarr_cleanup_drive_schedule_interval_seconds=120,
        failed_import_sonarr_cleanup_drive_schedule_enabled=False,
    )
    specs = failed_import_cleanup_drive_schedule_specs(s)
    assert len(specs) == 1
    assert specs[0][0] == "radarr_failed_import_cleanup_drive"
    assert specs[0][1] == 120.0
    assert specs[0][2] is enqueue_radarr_failed_import_cleanup_drive_job


def test_schedule_specs_sonarr_only_when_sonarr_enabled() -> None:
    base = _base_settings()
    s = replace(
        base,
        failed_import_radarr_cleanup_drive_schedule_enabled=False,
        failed_import_sonarr_cleanup_drive_schedule_enabled=True,
        failed_import_sonarr_cleanup_drive_schedule_interval_seconds=90,
    )
    specs = failed_import_cleanup_drive_schedule_specs(s)
    assert len(specs) == 1
    assert specs[0][0] == "sonarr_failed_import_cleanup_drive"
    assert specs[0][1] == 90.0
    assert specs[0][2] is enqueue_sonarr_failed_import_cleanup_drive_job


def test_schedule_specs_both_independent_when_both_enabled() -> None:
    base = _base_settings()
    s = replace(
        base,
        failed_import_radarr_cleanup_drive_schedule_enabled=True,
        failed_import_radarr_cleanup_drive_schedule_interval_seconds=100,
        failed_import_sonarr_cleanup_drive_schedule_enabled=True,
        failed_import_sonarr_cleanup_drive_schedule_interval_seconds=200,
    )
    specs = failed_import_cleanup_drive_schedule_specs(s)
    assert len(specs) == 2
    assert specs[0][1] != specs[1][1]


def test_schedule_specs_empty_when_both_disabled() -> None:
    base = _base_settings()
    s = replace(
        base,
        failed_import_radarr_cleanup_drive_schedule_enabled=False,
        failed_import_sonarr_cleanup_drive_schedule_enabled=False,
    )
    assert failed_import_cleanup_drive_schedule_specs(s) == []


def test_disabling_radarr_does_not_imply_sonarr_spec() -> None:
    base = _base_settings()
    s = replace(
        base,
        failed_import_radarr_cleanup_drive_schedule_enabled=False,
        failed_import_sonarr_cleanup_drive_schedule_enabled=True,
        failed_import_sonarr_cleanup_drive_schedule_interval_seconds=60,
    )
    specs = failed_import_cleanup_drive_schedule_specs(s)
    assert len(specs) == 1
    assert specs[0][2] is enqueue_sonarr_failed_import_cleanup_drive_job


def test_periodic_radarr_enqueue_dedupes_across_ticks(session_factory) -> None:
    async def _run() -> None:
        stop = asyncio.Event()
        t0 = asyncio.create_task(
            run_periodic_refiner_cleanup_drive_enqueue(
                session_factory,
                stop_event=stop,
                interval_seconds=0.06,
                log_label="test_radarr",
                enqueue_fn=enqueue_radarr_failed_import_cleanup_drive_job,
            ),
        )
        await asyncio.sleep(0.2)
        stop.set()
        await t0

    asyncio.run(_run())

    with session_factory() as s:
        n = s.scalar(
            select(func.count()).select_from(RefinerJob).where(
                RefinerJob.job_kind == FAILED_IMPORT_JOB_KIND_RADARR_CLEANUP_DRIVE,
            ),
        )
    assert n == 1


def test_periodic_radarr_production_label_one_fetcher_pass_queued_across_ticks(
    session_factory,
    failed_import_queue_worker_runtime_bundle,
) -> None:
    """Production log_label: emit timed pass-queued activity only when the dedupe job row is first created."""

    async def _run() -> None:
        stop = asyncio.Event()
        t0 = asyncio.create_task(
            run_periodic_refiner_cleanup_drive_enqueue(
                session_factory,
                stop_event=stop,
                interval_seconds=0.06,
                log_label="radarr_failed_import_cleanup_drive",
                enqueue_fn=enqueue_radarr_failed_import_cleanup_drive_job,
                timed_failed_import_pass_queued=failed_import_queue_worker_runtime_bundle.timed_schedule_pass_queued,
            ),
        )
        await asyncio.sleep(0.2)
        stop.set()
        await t0

    asyncio.run(_run())

    with session_factory() as s:
        n_pass = s.scalar(
            select(func.count()).select_from(ActivityEvent).where(
                ActivityEvent.module == "fetcher",
                ActivityEvent.event_type == act_c.FETCHER_FAILED_IMPORT_PASS_QUEUED,
            ),
        )
        assert n_pass == 1


def test_periodic_sonarr_enqueue_runs_independently(session_factory) -> None:
    async def _run() -> None:
        stop = asyncio.Event()
        t0 = asyncio.create_task(
            run_periodic_refiner_cleanup_drive_enqueue(
                session_factory,
                stop_event=stop,
                interval_seconds=0.06,
                log_label="test_sonarr",
                enqueue_fn=enqueue_sonarr_failed_import_cleanup_drive_job,
            ),
        )
        await asyncio.sleep(0.2)
        stop.set()
        await t0

    asyncio.run(_run())

    with session_factory() as s:
        n = s.scalar(
            select(func.count()).select_from(RefinerJob).where(
                RefinerJob.job_kind == FAILED_IMPORT_JOB_KIND_SONARR_CLEANUP_DRIVE,
            ),
        )
    assert n == 1


def test_start_schedule_tasks_respects_settings_independence(session_factory) -> None:
    async def _run() -> None:
        base = _base_settings()
        settings = replace(
            base,
            failed_import_radarr_cleanup_drive_schedule_enabled=True,
            failed_import_radarr_cleanup_drive_schedule_interval_seconds=3600,
            failed_import_sonarr_cleanup_drive_schedule_enabled=False,
        )
        stop = asyncio.Event()
        tasks = start_refiner_cleanup_drive_enqueue_schedule_tasks(
            session_factory,
            stop_event=stop,
            timed_failed_import_pass_queued=NoOpFailedImportTimedSchedulePassQueuedPort(),
            schedule_specs=failed_import_cleanup_drive_schedule_specs(settings),
        )
        assert len(tasks) == 1
        stop.set()
        await stop_refiner_cleanup_drive_enqueue_schedule_tasks(tasks)

    asyncio.run(_run())


def test_periodic_enqueue_failure_then_recovery_still_one_row(
    session_factory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        periodic_enqueue_mod,
        "REFINER_SCHEDULE_ENQUEUE_FAILURE_COOLDOWN_SECONDS",
        0.05,
    )
    n_ok = 0

    def flaky_enqueue(session: Session) -> RefinerJob:
        nonlocal n_ok
        n_ok += 1
        if n_ok == 1:
            raise RuntimeError("transient enqueue failure")
        return enqueue_radarr_failed_import_cleanup_drive_job(session)

    async def _run() -> None:
        stop = asyncio.Event()
        t0 = asyncio.create_task(
            run_periodic_refiner_cleanup_drive_enqueue(
                session_factory,
                stop_event=stop,
                interval_seconds=0.06,
                log_label="test_radarr_flaky",
                enqueue_fn=flaky_enqueue,
            ),
        )
        await asyncio.sleep(0.35)
        stop.set()
        await t0

    asyncio.run(_run())
    assert n_ok >= 2
    with session_factory() as s:
        n = s.scalar(
            select(func.count()).select_from(RefinerJob).where(
                RefinerJob.job_kind == FAILED_IMPORT_JOB_KIND_RADARR_CLEANUP_DRIVE,
            ),
        )
    assert n == 1


def test_radarr_enqueue_always_fails_sonarr_schedule_still_enqueues(
    session_factory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        periodic_enqueue_mod,
        "REFINER_SCHEDULE_ENQUEUE_FAILURE_COOLDOWN_SECONDS",
        0.05,
    )

    def broken_radarr(_session: Session) -> RefinerJob:
        raise RuntimeError("radarr config path broken")

    async def _run() -> None:
        stop = asyncio.Event()
        t_radarr = asyncio.create_task(
            run_periodic_refiner_cleanup_drive_enqueue(
                session_factory,
                stop_event=stop,
                interval_seconds=0.06,
                log_label="radarr_broken",
                enqueue_fn=broken_radarr,
            ),
        )
        t_sonarr = asyncio.create_task(
            run_periodic_refiner_cleanup_drive_enqueue(
                session_factory,
                stop_event=stop,
                interval_seconds=0.06,
                log_label="sonarr_ok",
                enqueue_fn=enqueue_sonarr_failed_import_cleanup_drive_job,
            ),
        )
        await asyncio.sleep(0.25)
        stop.set()
        await asyncio.gather(t_radarr, t_sonarr)

    asyncio.run(_run())
    with session_factory() as s:
        r = s.scalar(
            select(func.count()).select_from(RefinerJob).where(
                RefinerJob.job_kind == FAILED_IMPORT_JOB_KIND_RADARR_CLEANUP_DRIVE,
            ),
        )
        so = s.scalar(
            select(func.count()).select_from(RefinerJob).where(
                RefinerJob.job_kind == FAILED_IMPORT_JOB_KIND_SONARR_CLEANUP_DRIVE,
            ),
        )
    assert r == 0
    assert so == 1


def test_stop_schedule_tasks_does_not_hang(session_factory) -> None:
    async def _run() -> None:
        stop = asyncio.Event()
        tasks = [
            asyncio.create_task(
                run_periodic_refiner_cleanup_drive_enqueue(
                    session_factory,
                    stop_event=stop,
                    interval_seconds=60.0,
                    log_label="slow_tick",
                    enqueue_fn=enqueue_radarr_failed_import_cleanup_drive_job,
                ),
            ),
        ]
        stop.set()
        await asyncio.wait_for(
            stop_refiner_cleanup_drive_enqueue_schedule_tasks(tasks),
            timeout=5.0,
        )

    asyncio.run(_run())
