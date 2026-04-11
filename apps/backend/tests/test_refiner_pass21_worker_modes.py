"""Refiner ``refiner_worker_count`` modes (0 / 1 / >1) and multi-worker guardrails.

Contract-driven SQLite-backed tests; no new job kinds. Multi-worker remains a guarded capability;
default worker_count stays 1; 0 is explicit disable.
"""

from __future__ import annotations

import asyncio
import threading
from unittest.mock import patch
from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from mediamop.core.config import MediaMopSettings
from mediamop.core.db import Base
from mediamop.modules.refiner.jobs_model import RefinerJob, RefinerJobStatus
from mediamop.modules.refiner.jobs_ops import (
    claim_next_eligible_refiner_job,
    fail_leased_refiner_job_after_complete_failure,
    refiner_enqueue_or_get_job,
)
from mediamop.modules.fetcher.failed_import_refiner_job_handlers import build_failed_import_refiner_job_handlers
from mediamop.modules.fetcher.radarr_failed_import_cleanup_job import REFINER_JOB_KIND_RADARR_FAILED_IMPORT_CLEANUP_DRIVE
from mediamop.modules.fetcher.sonarr_failed_import_cleanup_job import REFINER_JOB_KIND_SONARR_FAILED_IMPORT_CLEANUP_DRIVE
from mediamop.modules.refiner import worker_loop as refiner_worker_loop_mod
from mediamop.modules.refiner.worker_loop import (
    process_one_refiner_job,
    start_refiner_worker_background_tasks,
    stop_refiner_worker_background_tasks,
)

import mediamop.modules.refiner.jobs_model  # noqa: F401
import mediamop.platform.activity.models  # noqa: F401
import mediamop.platform.auth.models  # noqa: F401


@pytest.fixture
def jobs_engine(tmp_path):
    url = f"sqlite:///{tmp_path / 'pass21.sqlite'}"
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


def _t0() -> datetime:
    return datetime(2026, 4, 11, 12, 0, 0, tzinfo=timezone.utc)


def test_default_refiner_worker_count_from_env_unset_is_one(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MEDIAMOP_REFINER_WORKER_COUNT", raising=False)
    assert MediaMopSettings.load().refiner_worker_count == 1


def test_start_refiner_worker_background_tasks_zero_spawns_no_tasks(
    session_factory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        refiner_worker_loop_mod,
        "REFINER_WORKER_IDLE_SLEEP_SECONDS",
        0.05,
    )
    base = MediaMopSettings.load()
    settings = replace(base, refiner_worker_count=0)

    async def _run() -> None:
        stop, tasks = start_refiner_worker_background_tasks(session_factory, settings)
        assert tasks == []
        stop.set()
        await stop_refiner_worker_background_tasks(stop, tasks)

    asyncio.run(_run())


def test_start_refiner_worker_count_gt_one_emits_guard_warning(
    session_factory,
    monkeypatch: pytest.MonkeyPatch,
    failed_import_refiner_runtime_bundle,
) -> None:
    monkeypatch.setattr(
        refiner_worker_loop_mod,
        "REFINER_WORKER_IDLE_SLEEP_SECONDS",
        0.05,
    )
    base = MediaMopSettings.load()
    settings = replace(base, refiner_worker_count=3)

    async def _run() -> None:
        handlers = build_failed_import_refiner_job_handlers(
            settings,
            session_factory,
            failed_import_runtime=failed_import_refiner_runtime_bundle,
        )
        stop, tasks = start_refiner_worker_background_tasks(
            session_factory,
            settings,
            job_handlers=handlers,
        )
        assert len(tasks) == 3
        stop.set()
        await stop_refiner_worker_background_tasks(stop, tasks)

    with patch.object(refiner_worker_loop_mod.logger, "warning") as mock_warn:
        asyncio.run(_run())
    assert mock_warn.called
    texts: list[str] = []
    for c in mock_warn.call_args_list:
        if not c.args:
            continue
        if len(c.args) == 1:
            texts.append(str(c.args[0]))
        else:
            texts.append(c.args[0] % tuple(c.args[1:]))
    assert any("guarded capability" in t for t in texts)
    assert any("refiner_worker_count=3" in t for t in texts)


def test_concurrent_process_one_only_one_handler_runs_for_single_job(session_factory) -> None:
    t0 = _t0()
    invocations: list[int] = []
    lock = threading.Lock()

    def _h(ctx) -> None:
        with lock:
            invocations.append(ctx.id)

    with session_factory() as s:
        refiner_enqueue_or_get_job(s, dedupe_key="pass21-one-exec", job_kind="pass21.kind")
        s.commit()

    barrier = threading.Barrier(2)

    def _run(owner: str) -> None:
        barrier.wait()
        process_one_refiner_job(
            session_factory,
            lease_owner=owner,
            job_handlers={"pass21.kind": _h},
            now=t0,
            lease_seconds=3600,
        )

    t1 = threading.Thread(target=_run, args=("w-a",))
    t2 = threading.Thread(target=_run, args=("w-b",))
    t1.start()
    t2.start()
    t1.join()
    t2.join()

    assert len(invocations) == 1
    with session_factory() as s:
        row = s.get(RefinerJob, 1)
        assert row is not None
        assert row.status == RefinerJobStatus.COMPLETED.value


def test_concurrent_enqueue_same_dedupe_with_racing_process_one_leaves_one_completed_row(
    session_factory,
) -> None:
    t0 = _t0()
    errors: list[BaseException] = []
    enq_barrier = threading.Barrier(2)

    def _enqueue() -> None:
        try:
            enq_barrier.wait()
            with session_factory() as s:
                refiner_enqueue_or_get_job(
                    s,
                    dedupe_key="pass21-dedupe-race",
                    job_kind="pass21.d",
                )
                s.commit()
        except BaseException as e:
            errors.append(e)

    def _h(_ctx) -> None:
        return None

    enq_threads = [threading.Thread(target=_enqueue), threading.Thread(target=_enqueue)]
    for t in enq_threads:
        t.start()
    for t in enq_threads:
        t.join()
    assert not errors

    proc_barrier = threading.Barrier(2)

    def _process(owner: str) -> None:
        try:
            proc_barrier.wait()
            process_one_refiner_job(
                session_factory,
                lease_owner=owner,
                job_handlers={"pass21.d": _h},
                now=t0,
                lease_seconds=3600,
            )
        except BaseException as e:
            errors.append(e)

    proc_threads = [
        threading.Thread(target=_process, args=("p1",)),
        threading.Thread(target=_process, args=("p2",)),
    ]
    for t in proc_threads:
        t.start()
    for t in proc_threads:
        t.join()
    assert not errors
    with session_factory() as s:
        rows = list(s.scalars(select(RefinerJob)).all())
        assert len(rows) == 1
        assert rows[0].dedupe_key == "pass21-dedupe-race"
        assert rows[0].status == RefinerJobStatus.COMPLETED.value


def test_radarr_and_sonarr_real_job_kinds_process_concurrently_without_cross_mutation(
    session_factory,
) -> None:
    t0 = _t0()
    touched: dict[str, list[int]] = {"radarr": [], "sonarr": []}
    lock = threading.Lock()

    def _rad(ctx) -> None:
        with lock:
            touched["radarr"].append(ctx.id)
            assert ctx.job_kind == REFINER_JOB_KIND_RADARR_FAILED_IMPORT_CLEANUP_DRIVE

    def _son(ctx) -> None:
        with lock:
            touched["sonarr"].append(ctx.id)
            assert ctx.job_kind == REFINER_JOB_KIND_SONARR_FAILED_IMPORT_CLEANUP_DRIVE

    handlers = {
        REFINER_JOB_KIND_RADARR_FAILED_IMPORT_CLEANUP_DRIVE: _rad,
        REFINER_JOB_KIND_SONARR_FAILED_IMPORT_CLEANUP_DRIVE: _son,
    }

    with session_factory() as s:
        refiner_enqueue_or_get_job(
            s,
            dedupe_key="pass21-isolate-rad",
            job_kind=REFINER_JOB_KIND_RADARR_FAILED_IMPORT_CLEANUP_DRIVE,
        )
        refiner_enqueue_or_get_job(
            s,
            dedupe_key="pass21-isolate-son",
            job_kind=REFINER_JOB_KIND_SONARR_FAILED_IMPORT_CLEANUP_DRIVE,
        )
        s.commit()

    barrier = threading.Barrier(2)

    def _run(owner: str) -> None:
        barrier.wait()
        process_one_refiner_job(
            session_factory,
            lease_owner=owner,
            job_handlers=handlers,
            now=t0,
            lease_seconds=3600,
        )

    a = threading.Thread(target=_run, args=("iso-1",))
    b = threading.Thread(target=_run, args=("iso-2",))
    a.start()
    b.start()
    a.join()
    b.join()

    assert sorted(touched["radarr"]) == [1]
    assert sorted(touched["sonarr"]) == [2]
    with session_factory() as s:
        r1 = s.get(RefinerJob, 1)
        r2 = s.get(RefinerJob, 2)
        assert r1.status == RefinerJobStatus.COMPLETED.value
        assert r2.status == RefinerJobStatus.COMPLETED.value


def test_concurrent_workers_radarr_handler_failure_does_not_block_sonarr_completion(
    session_factory,
) -> None:
    t0 = _t0()

    def _rad_fail(_ctx) -> None:
        raise RuntimeError("radarr handler synthetic failure")

    def _son_ok(_ctx) -> None:
        return None

    handlers = {
        REFINER_JOB_KIND_RADARR_FAILED_IMPORT_CLEANUP_DRIVE: _rad_fail,
        REFINER_JOB_KIND_SONARR_FAILED_IMPORT_CLEANUP_DRIVE: _son_ok,
    }

    with session_factory() as s:
        refiner_enqueue_or_get_job(
            s,
            dedupe_key="pass21-fail-rad",
            job_kind=REFINER_JOB_KIND_RADARR_FAILED_IMPORT_CLEANUP_DRIVE,
            max_attempts=1,
        )
        refiner_enqueue_or_get_job(
            s,
            dedupe_key="pass21-ok-son",
            job_kind=REFINER_JOB_KIND_SONARR_FAILED_IMPORT_CLEANUP_DRIVE,
        )
        s.commit()

    barrier = threading.Barrier(2)

    def _run(owner: str) -> None:
        barrier.wait()
        process_one_refiner_job(
            session_factory,
            lease_owner=owner,
            job_handlers=handlers,
            now=t0,
            lease_seconds=3600,
        )

    a = threading.Thread(target=_run, args=("fx-1",))
    b = threading.Thread(target=_run, args=("fx-2",))
    a.start()
    b.start()
    a.join()
    b.join()

    with session_factory() as s:
        rad = s.get(RefinerJob, 1)
        son = s.get(RefinerJob, 2)
        assert rad.status == RefinerJobStatus.FAILED.value
        assert "synthetic failure" in (rad.last_error or "")
        assert son.status == RefinerJobStatus.COMPLETED.value


def test_parallel_claim_next_skips_handler_ok_finalize_failed_prefers_pending(
    session_factory,
) -> None:
    t0 = _t0()
    with session_factory() as s:
        refiner_enqueue_or_get_job(s, dedupe_key="pass21-fin", job_kind="z")
        refiner_enqueue_or_get_job(s, dedupe_key="pass21-pend", job_kind="z")
        s.commit()
    with session_factory() as s:
        j = claim_next_eligible_refiner_job(
            s,
            lease_owner="solo",
            lease_expires_at=t0 + timedelta(hours=1),
            now=t0,
        )
        assert j is not None
        assert j.id == 1
        assert fail_leased_refiner_job_after_complete_failure(
            s,
            job_id=1,
            lease_owner="solo",
            error_message="refiner_terminalization_failure: pass21",
            now=t0,
        )
        s.commit()

    claimed: list[int | None] = []
    barrier = threading.Barrier(4)

    def _claim() -> None:
        barrier.wait()
        with session_factory() as s2:
            j2 = claim_next_eligible_refiner_job(
                s2,
                lease_owner=threading.current_thread().name,
                lease_expires_at=t0 + timedelta(hours=1),
                now=t0,
            )
            s2.commit()
            claimed.append(j2.id if j2 else None)

    threads = [threading.Thread(target=_claim, name=f"c{i}") for i in range(4)]
    for th in threads:
        th.start()
    for th in threads:
        th.join()

    non_null = [x for x in claimed if x is not None]
    assert non_null == [2]
    with session_factory() as s:
        fin = s.get(RefinerJob, 1)
        assert fin.status == RefinerJobStatus.HANDLER_OK_FINALIZE_FAILED.value
        pend = s.get(RefinerJob, 2)
        assert pend.status == RefinerJobStatus.LEASED.value


def test_stop_multiple_refiner_workers_completes_within_timeout(
    session_factory,
    monkeypatch: pytest.MonkeyPatch,
    failed_import_refiner_runtime_bundle,
) -> None:
    monkeypatch.setattr(
        refiner_worker_loop_mod,
        "REFINER_WORKER_IDLE_SLEEP_SECONDS",
        0.05,
    )
    base = MediaMopSettings.load()
    settings = replace(base, refiner_worker_count=4)

    async def _run() -> None:
        handlers = build_failed_import_refiner_job_handlers(
            settings,
            session_factory,
            failed_import_runtime=failed_import_refiner_runtime_bundle,
        )
        stop, tasks = start_refiner_worker_background_tasks(
            session_factory,
            settings,
            job_handlers=handlers,
        )
        assert len(tasks) == 4
        stop.set()
        await asyncio.wait_for(
            stop_refiner_worker_background_tasks(stop, tasks),
            timeout=5.0,
        )

    asyncio.run(_run())
