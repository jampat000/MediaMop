from __future__ import annotations

import asyncio
from dataclasses import replace
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from mediamop.core.config import MediaMopSettings
from mediamop.core.db import Base
from mediamop.modules.dashboard.service import build_dashboard_status
from mediamop.modules.refiner import worker_loop as refiner_worker_loop
from mediamop.modules.refiner.worker_loop import start_refiner_worker_background_tasks, stop_refiner_worker_background_tasks
from mediamop.platform.jobs.worker_health import (
    build_worker_health_snapshot,
    reset_worker_health_for_tests,
    worker_heartbeat,
    worker_started,
    worker_stopped,
)
from mediamop.platform.readiness.service import build_readiness


@pytest.fixture(autouse=True)
def _reset_worker_health() -> None:
    reset_worker_health_for_tests()


@pytest.fixture
def session_factory(tmp_path: Path) -> sessionmaker[Session]:
    engine = create_engine(
        f"sqlite:///{tmp_path / 'worker_health.sqlite'}",
        connect_args={"check_same_thread": False},
        future=True,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, class_=Session, autoflush=False, autocommit=False, expire_on_commit=False, future=True)


def test_worker_health_detects_missing_stale_and_stopped_workers() -> None:
    worker_started("refiner", 0)
    worker_heartbeat("refiner", 0)
    worker_started("pruner", 0)
    worker_stopped("pruner", 0)

    snapshot = {
        row.module: row
        for row in build_worker_health_snapshot(
            expected_workers={"refiner": 2, "pruner": 1, "subber": 0},
            stale_after_seconds=-1,
        )
    }

    assert snapshot["refiner"].status == "degraded"
    assert snapshot["refiner"].stale_workers == 2
    assert snapshot["pruner"].status == "degraded"
    assert snapshot["pruner"].stopped_workers == 1
    assert snapshot["subber"].status == "disabled"


def test_refiner_worker_emits_heartbeat(session_factory, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(refiner_worker_loop, "REFINER_WORKER_IDLE_SLEEP_SECONDS", 0.01)
    settings = replace(MediaMopSettings.load(), refiner_worker_count=1)

    async def _run() -> None:
        stop, tasks = start_refiner_worker_background_tasks(
            session_factory,
            settings,
            job_handlers={"refiner.test.health.v1": lambda ctx: None},
        )
        await asyncio.sleep(0.05)
        snapshot = build_worker_health_snapshot(expected_workers={"refiner": 1})
        assert snapshot[0].status == "healthy"
        await stop_refiner_worker_background_tasks(stop, tasks)
        stopped = build_worker_health_snapshot(expected_workers={"refiner": 1})
        assert stopped[0].status == "degraded"
        assert stopped[0].stopped_workers == 1

    asyncio.run(_run())


def test_dashboard_marks_system_unhealthy_when_worker_degraded(session_factory) -> None:
    settings = replace(MediaMopSettings.load(), refiner_worker_count=1, pruner_worker_count=0, subber_worker_count=0)
    with session_factory() as session:
        out = build_dashboard_status(session, settings)
    assert out.system.healthy is False
    assert any(row.module == "refiner" and row.status == "degraded" for row in out.system.worker_health)


def test_readiness_fails_when_expected_worker_has_no_heartbeat(session_factory) -> None:
    class State:
        startup_started_at = 0.0
        startup_ready = True
        settings = replace(MediaMopSettings.load(), refiner_worker_count=1, pruner_worker_count=0, subber_worker_count=0)
        engine = object()
        session_factory = object()

    out = build_readiness(State())
    assert out.ready is False
    assert out.status == "failed"
    assert any(step.name == "workers" and step.status == "failed" for step in out.steps)
    assert any(row.module == "refiner" and row.status == "degraded" for row in out.worker_health)
