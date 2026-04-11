"""Fetcher in-process worker loop: task fan-out and lifecycle (Fetcher-local)."""

from __future__ import annotations

import asyncio
from dataclasses import replace

import pytest
from sqlalchemy.orm import Session, sessionmaker

from mediamop.core.config import MediaMopSettings
from mediamop.modules.fetcher.failed_import_queue_job_handlers import build_failed_import_queue_job_handlers
from mediamop.modules.fetcher import fetcher_worker_loop as fetcher_worker_loop_mod
from mediamop.modules.fetcher.fetcher_worker_loop import (
    start_fetcher_worker_background_tasks,
    stop_fetcher_worker_background_tasks,
)

import mediamop.modules.fetcher.fetcher_jobs_model  # noqa: F401 -- registers ``fetcher_jobs`` on ``Base``
import mediamop.platform.activity.models  # noqa: F401
import mediamop.platform.auth.models  # noqa: F401
from mediamop.core.db import Base


@pytest.fixture
def jobs_engine(tmp_path):
    from sqlalchemy import create_engine

    url = f"sqlite:///{tmp_path / 'fetcher_worker.sqlite'}"
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


def test_fetcher_worker_count_defaults_to_one(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MEDIAMOP_FETCHER_WORKER_COUNT", raising=False)
    s = MediaMopSettings.load()
    assert s.fetcher_worker_count == 1


def test_spawn_fetcher_worker_task_count_matches_settings(
    session_factory,
    monkeypatch: pytest.MonkeyPatch,
    failed_import_queue_worker_runtime_bundle,
) -> None:
    monkeypatch.setattr(
        "mediamop.modules.fetcher.fetcher_worker_loop.FETCHER_WORKER_IDLE_SLEEP_SECONDS",
        0.05,
    )
    base = MediaMopSettings.load()
    settings = replace(base, fetcher_worker_count=2)

    async def _run() -> None:
        handlers = build_failed_import_queue_job_handlers(
            settings,
            session_factory,
            failed_import_runtime=failed_import_queue_worker_runtime_bundle,
        )
        stop, tasks = start_fetcher_worker_background_tasks(
            session_factory,
            settings,
            job_handlers=handlers,
        )
        assert len(tasks) == 2
        stop.set()
        await stop_fetcher_worker_background_tasks(stop, tasks)

    asyncio.run(_run())


def test_start_and_stop_fetcher_workers_completes_within_timeout(
    session_factory,
    monkeypatch: pytest.MonkeyPatch,
    failed_import_queue_worker_runtime_bundle,
) -> None:
    monkeypatch.setattr(
        fetcher_worker_loop_mod,
        "FETCHER_WORKER_IDLE_SLEEP_SECONDS",
        0.05,
    )
    base = MediaMopSettings.load()
    settings = replace(base, fetcher_worker_count=1)

    async def _run() -> None:
        handlers = build_failed_import_queue_job_handlers(
            settings,
            session_factory,
            failed_import_runtime=failed_import_queue_worker_runtime_bundle,
        )
        stop, tasks = start_fetcher_worker_background_tasks(
            session_factory,
            settings,
            job_handlers=handlers,
        )
        stop.set()
        await asyncio.wait_for(
            stop_fetcher_worker_background_tasks(stop, tasks),
            timeout=5.0,
        )

    asyncio.run(_run())
