"""In-process Refiner worker loop and Refiner worker-count settings (Refiner-local)."""

from __future__ import annotations

import asyncio
from dataclasses import replace
from datetime import datetime, timezone
from unittest.mock import patch

import pytest
from sqlalchemy.orm import Session, sessionmaker

from mediamop.core.config import MediaMopSettings
from mediamop.modules.refiner.jobs_model import RefinerJob, RefinerJobStatus
from mediamop.modules.refiner.jobs_ops import refiner_enqueue_or_get_job
from mediamop.modules.refiner.worker_limits import clamp_refiner_worker_count
from mediamop.modules.refiner import worker_loop as refiner_worker_loop_mod
from mediamop.modules.refiner.jobs_ops import complete_claimed_refiner_job as real_complete_claimed
from mediamop.modules.refiner.worker_loop import (
    process_one_refiner_job,
    refiner_worker_run_forever,
    start_refiner_worker_background_tasks,
    stop_refiner_worker_background_tasks,
)

import mediamop.modules.refiner.jobs_model  # noqa: F401
import mediamop.platform.activity.models  # noqa: F401
import mediamop.platform.auth.models  # noqa: F401
from mediamop.core.db import Base


@pytest.fixture
def jobs_engine(tmp_path):
    from sqlalchemy import create_engine

    url = f"sqlite:///{tmp_path / 'worker.sqlite'}"
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


def test_refiner_worker_count_defaults_to_eight_slots(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MEDIAMOP_REFINER_WORKER_COUNT", raising=False)
    s = MediaMopSettings.load()
    assert s.refiner_worker_count == 8


def test_refiner_worker_count_clamps_low_and_high(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MEDIAMOP_REFINER_WORKER_COUNT", "0")
    assert MediaMopSettings.load().refiner_worker_count == 0
    monkeypatch.setenv("MEDIAMOP_REFINER_WORKER_COUNT", "99")
    assert MediaMopSettings.load().refiner_worker_count == 8


def test_clamp_refiner_worker_count_unit() -> None:
    assert clamp_refiner_worker_count(-1) == 1
    assert clamp_refiner_worker_count(0) == 0
    assert clamp_refiner_worker_count(1) == 1
    assert clamp_refiner_worker_count(8) == 8
    assert clamp_refiner_worker_count(9) == 8


def test_start_refiner_worker_background_tasks_zero_spawns_no_tasks_even_with_handlers(
    session_factory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Lifespan passes a handler map while ``refiner_worker_count`` is 0 — still no asyncio workers."""

    monkeypatch.setattr(
        refiner_worker_loop_mod,
        "REFINER_WORKER_IDLE_SLEEP_SECONDS",
        0.05,
    )
    base = MediaMopSettings.load()
    settings = replace(base, refiner_worker_count=0)
    dummy_handlers = {"refiner.candidate_gate.v1": lambda ctx: None}

    async def _run() -> None:
        stop, tasks = start_refiner_worker_background_tasks(
            session_factory,
            settings,
            job_handlers=dummy_handlers,
        )
        assert tasks == []
        stop.set()
        await stop_refiner_worker_background_tasks(stop, tasks)

    asyncio.run(_run())


def test_refiner_worker_slots_are_gated_by_max_concurrent_files(
    session_factory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        refiner_worker_loop_mod,
        "REFINER_WORKER_IDLE_SLEEP_SECONDS",
        0.01,
    )
    base = MediaMopSettings.load()
    settings = replace(base, refiner_worker_count=8)
    observed: list[int] = []

    async def _fake_worker_run_forever(*_args, **kwargs) -> None:
        idx = int(kwargs["worker_index"])
        getter = kwargs["max_concurrent_files_getter"]
        assert getter is not None
        if idx < getter():
            observed.append(idx)

    async def _run() -> None:
        with patch(
            "mediamop.modules.refiner.worker_loop.refiner_worker_run_forever",
            side_effect=_fake_worker_run_forever,
        ):
            stop, tasks = start_refiner_worker_background_tasks(
                session_factory,
                settings,
                job_handlers={"refiner.candidate_gate.v1": lambda ctx: None},
                max_concurrent_files_getter=lambda: 3,
            )
            await asyncio.gather(*tasks)
            await stop_refiner_worker_background_tasks(stop, tasks)

    asyncio.run(_run())
    assert observed == [0, 1, 2]


def test_process_one_idle_when_no_jobs(session_factory) -> None:
    out = process_one_refiner_job(
        session_factory,
        lease_owner="test-owner",
        job_handlers={},
    )
    assert out == "idle"


def test_process_one_completes_with_success_handler(session_factory) -> None:
    t0 = datetime(2026, 4, 10, 12, 0, 0, tzinfo=timezone.utc)
    with session_factory() as s:
        refiner_enqueue_or_get_job(s, dedupe_key="d1", job_kind="refiner.test.ok.v1", max_attempts=3)
        s.commit()

    def _ok(ctx) -> None:
        assert ctx.job_kind == "refiner.test.ok.v1"

    out = process_one_refiner_job(
        session_factory,
        lease_owner="w",
        job_handlers={"refiner.test.ok.v1": _ok},
        now=t0,
        lease_seconds=3600,
    )
    assert out == "processed"
    with session_factory() as s:
        row = s.get(RefinerJob, 1)
        assert row.status == RefinerJobStatus.COMPLETED.value


def test_process_one_fail_path_on_handler_error(session_factory) -> None:
    t0 = datetime(2026, 4, 10, 12, 0, 0, tzinfo=timezone.utc)
    with session_factory() as s:
        refiner_enqueue_or_get_job(
            s,
            dedupe_key="d2",
            job_kind="refiner.test.bad.v1",
            max_attempts=1,
        )
        s.commit()

    def _bad(_ctx) -> None:
        raise RuntimeError("boom")

    out = process_one_refiner_job(
        session_factory,
        lease_owner="w",
        job_handlers={"refiner.test.bad.v1": _bad},
        now=t0,
        lease_seconds=3600,
    )
    assert out == "processed"
    with session_factory() as s:
        row = s.get(RefinerJob, 1)
        assert row.status == RefinerJobStatus.FAILED.value
        assert "boom" in (row.last_error or "")


def test_process_one_missing_handler_fails_claimed_job(session_factory) -> None:
    t0 = datetime(2026, 4, 10, 12, 0, 0, tzinfo=timezone.utc)
    with session_factory() as s:
        refiner_enqueue_or_get_job(s, dedupe_key="d3", job_kind="refiner.test.unknown.v1")
        s.commit()

    out = process_one_refiner_job(
        session_factory,
        lease_owner="w",
        job_handlers={},
        now=t0,
        lease_seconds=3600,
    )
    assert out == "processed"
    with session_factory() as s:
        row = s.get(RefinerJob, 1)
        assert row.status == RefinerJobStatus.PENDING.value
        assert "refiner.test.unknown.v1" in (row.last_error or "")


def test_refiner_worker_loop_processes_one_job_then_stops(session_factory, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "mediamop.modules.refiner.worker_loop.REFINER_WORKER_IDLE_SLEEP_SECONDS",
        0.05,
    )
    t0 = datetime(2026, 4, 10, 12, 0, 0, tzinfo=timezone.utc)
    with session_factory() as s:
        refiner_enqueue_or_get_job(s, dedupe_key="loop1", job_kind="refiner.test.loop_ok.v1")
        s.commit()

    seen: list[str] = []

    def _h(ctx) -> None:
        seen.append(ctx.job_kind)

    async def _run() -> None:
        stop = asyncio.Event()
        task = asyncio.create_task(
            refiner_worker_run_forever(
                session_factory,
                worker_index=0,
                stop_event=stop,
                job_handlers={"refiner.test.loop_ok.v1": _h},
                idle_sleep_seconds=0.05,
                lease_seconds=3600,
            ),
        )
        for _ in range(200):
            if seen:
                break
            await asyncio.sleep(0.01)
        stop.set()
        await asyncio.wait_for(task, timeout=5.0)

    asyncio.run(_run())
    assert seen == ["refiner.test.loop_ok.v1"]
    with session_factory() as s:
        row = s.get(RefinerJob, 1)
        assert row.status == RefinerJobStatus.COMPLETED.value


def test_worker_survives_tick_exception_then_processes_idle(
    session_factory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        refiner_worker_loop_mod,
        "REFINER_WORKER_TICK_ERROR_BACKOFF_SECONDS",
        0.05,
    )
    monkeypatch.setattr(
        refiner_worker_loop_mod,
        "REFINER_WORKER_IDLE_SLEEP_SECONDS",
        0.05,
    )
    tick_calls = 0

    def _tick_side_effect(*_a, **_kw) -> str:
        nonlocal tick_calls
        tick_calls += 1
        if tick_calls == 1:
            raise RuntimeError("synthetic tick crash")
        return "idle"

    async def _run() -> None:
        stop = asyncio.Event()
        with patch.object(
            refiner_worker_loop_mod,
            "process_one_refiner_job",
            side_effect=_tick_side_effect,
        ):
            task = asyncio.create_task(
                refiner_worker_run_forever(
                    session_factory,
                    worker_index=0,
                    stop_event=stop,
                    job_handlers={},
                    idle_sleep_seconds=0.05,
                ),
            )
            for _ in range(500):
                if tick_calls >= 2:
                    break
                await asyncio.sleep(0.01)
            assert tick_calls >= 2, "worker should retry after tick exception"
            stop.set()
            await asyncio.wait_for(task, timeout=5.0)

    asyncio.run(_run())


def test_process_one_survives_complete_claim_raises(session_factory) -> None:
    t0 = datetime(2026, 4, 10, 12, 0, 0, tzinfo=timezone.utc)
    with session_factory() as s:
        refiner_enqueue_or_get_job(s, dedupe_key="d-complete-raise", job_kind="refiner.test.ok.v1", max_attempts=3)
        s.commit()

    def _ok(_ctx) -> None:
        return None

    with patch.object(
        refiner_worker_loop_mod,
        "complete_claimed_refiner_job",
        side_effect=RuntimeError("db write failed"),
    ):
        out = process_one_refiner_job(
            session_factory,
            lease_owner="w",
            job_handlers={"refiner.test.ok.v1": _ok},
            now=t0,
            lease_seconds=3600,
        )
    assert out == "processed"
    with session_factory() as s:
        row = s.get(RefinerJob, 1)
        assert row.status == RefinerJobStatus.HANDLER_OK_FINALIZE_FAILED.value
        assert row.attempt_count == 1
        assert row.lease_owner is None
        assert "refiner_terminalization_failure:" in (row.last_error or "")
        assert "db write failed" in (row.last_error or "")


def test_process_one_complete_refused_triggers_terminalization(session_factory) -> None:
    t0 = datetime(2026, 4, 10, 12, 0, 0, tzinfo=timezone.utc)
    with session_factory() as s:
        refiner_enqueue_or_get_job(s, dedupe_key="d-complete-false", job_kind="refiner.test.ok.v1", max_attempts=3)
        s.commit()

    def _ok(_ctx) -> None:
        return None

    with patch.object(
        refiner_worker_loop_mod,
        "complete_claimed_refiner_job",
        return_value=False,
    ):
        out = process_one_refiner_job(
            session_factory,
            lease_owner="w",
            job_handlers={"refiner.test.ok.v1": _ok},
            now=t0,
            lease_seconds=3600,
        )
    assert out == "processed"
    with session_factory() as s:
        row = s.get(RefinerJob, 1)
        assert row.status == RefinerJobStatus.HANDLER_OK_FINALIZE_FAILED.value
        assert "refiner_terminalization_failure:" in (row.last_error or "")
        assert "refused" in (row.last_error or "")


def test_terminalization_of_first_job_does_not_block_second_job_completion(session_factory) -> None:
    t0 = datetime(2026, 4, 10, 12, 0, 0, tzinfo=timezone.utc)
    with session_factory() as s:
        refiner_enqueue_or_get_job(s, dedupe_key="seq-a", job_kind="refiner.test.ok.v1", max_attempts=3)
        refiner_enqueue_or_get_job(s, dedupe_key="seq-b", job_kind="refiner.test.ok.v1", max_attempts=3)
        s.commit()

    def _ok(_ctx) -> None:
        return None

    def complete_shim(session, **kwargs: object) -> bool:
        job_id = int(kwargs["job_id"])
        if job_id == 1:
            raise RuntimeError("first job complete failed")
        return real_complete_claimed(
            session,
            job_id=job_id,
            lease_owner=str(kwargs["lease_owner"]),
            now=kwargs.get("now"),
        )

    with patch.object(
        refiner_worker_loop_mod,
        "complete_claimed_refiner_job",
        side_effect=complete_shim,
    ):
        assert (
            process_one_refiner_job(
                session_factory,
                lease_owner="w",
                job_handlers={"refiner.test.ok.v1": _ok},
                now=t0,
                lease_seconds=3600,
            )
            == "processed"
        )
        assert (
            process_one_refiner_job(
                session_factory,
                lease_owner="w",
                job_handlers={"refiner.test.ok.v1": _ok},
                now=t0,
                lease_seconds=3600,
            )
            == "processed"
        )
    with session_factory() as s:
        r1 = s.get(RefinerJob, 1)
        r2 = s.get(RefinerJob, 2)
        assert r1.status == RefinerJobStatus.HANDLER_OK_FINALIZE_FAILED.value
        assert "refiner_terminalization_failure:" in (r1.last_error or "")
        assert r2.status == RefinerJobStatus.COMPLETED.value


def test_worker_stays_alive_after_complete_failure_terminalization(
    session_factory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        refiner_worker_loop_mod,
        "REFINER_WORKER_IDLE_SLEEP_SECONDS",
        0.05,
    )
    t0 = datetime(2026, 4, 10, 12, 0, 0, tzinfo=timezone.utc)
    with session_factory() as s:
        refiner_enqueue_or_get_job(s, dedupe_key="w-term", job_kind="refiner.test.term.v1", max_attempts=3)
        s.commit()

    def _ok(_ctx) -> None:
        return None

    async def _run() -> None:
        stop = asyncio.Event()
        with patch.object(
            refiner_worker_loop_mod,
            "complete_claimed_refiner_job",
            side_effect=RuntimeError("complete unavailable"),
        ):
            task = asyncio.create_task(
                refiner_worker_run_forever(
                    session_factory,
                    worker_index=0,
                    stop_event=stop,
                    job_handlers={"refiner.test.term.v1": _ok},
                    idle_sleep_seconds=0.05,
                    lease_seconds=3600,
                ),
            )
            for _ in range(400):
                with session_factory() as s:
                    row = s.get(RefinerJob, 1)
                    if row is not None and row.status == RefinerJobStatus.HANDLER_OK_FINALIZE_FAILED.value:
                        break
                await asyncio.sleep(0.01)
            else:
                pytest.fail("expected terminalization to handler_ok_finalize_failed")
            stop.set()
            await asyncio.wait_for(task, timeout=5.0)

    asyncio.run(_run())
