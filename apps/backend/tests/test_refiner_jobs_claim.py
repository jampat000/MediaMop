"""Refiner Pass 13: refiner_jobs table — enqueue dedupe, atomic claim, lease, complete, fail."""

from __future__ import annotations

import threading
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from mediamop.core.db import Base
from mediamop.modules.refiner.jobs_model import RefinerJob, RefinerJobStatus
from mediamop.modules.refiner.jobs_ops import (
    claim_next_eligible_refiner_job,
    complete_claimed_refiner_job,
    fail_claimed_refiner_job,
    fail_leased_refiner_job_after_complete_failure,
    recover_handler_ok_finalize_failed_to_completed,
    refiner_enqueue_or_get_job,
)

# Register all ORM tables on Base.metadata (create_all parity with Alembic surface).
import mediamop.modules.refiner.jobs_model  # noqa: F401
import mediamop.platform.activity.models  # noqa: F401
import mediamop.platform.auth.models  # noqa: F401


@pytest.fixture
def jobs_engine(tmp_path):
    url = f"sqlite:///{tmp_path / 'refiner_jobs.sqlite'}"
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
    return datetime(2026, 4, 10, 12, 0, 0, tzinfo=timezone.utc)


def test_enqueue_duplicate_dedupe_key_returns_same_row(session_factory):
    fac = session_factory
    with fac() as s:
        a = refiner_enqueue_or_get_job(s, dedupe_key="k1", job_kind="test")
        s.commit()
        aid = a.id
    with fac() as s:
        b = refiner_enqueue_or_get_job(s, dedupe_key="k1", job_kind="test")
        s.commit()
    assert b.id == aid


def test_concurrent_enqueue_same_dedupe_key_single_row(session_factory):
    fac = session_factory
    barrier = threading.Barrier(2)
    ids: list[int] = []
    errors: list[BaseException] = []

    def run():
        try:
            barrier.wait()
            with fac() as s:
                j = refiner_enqueue_or_get_job(s, dedupe_key="race", job_kind="test")
                s.commit()
                ids.append(j.id)
        except BaseException as e:
            errors.append(e)

    t1 = threading.Thread(target=run)
    t2 = threading.Thread(target=run)
    t1.start()
    t2.start()
    t1.join()
    t2.join()
    assert not errors
    assert ids[0] == ids[1]


def test_second_claim_does_not_return_same_job_when_first_holds_lease(session_factory):
    fac = session_factory
    t0 = _t0()
    with fac() as s:
        refiner_enqueue_or_get_job(s, dedupe_key="solo", job_kind="test")
        s.commit()
    with fac() as s:
        j1 = claim_next_eligible_refiner_job(
            s,
            lease_owner="w1",
            lease_expires_at=t0 + timedelta(hours=1),
            now=t0,
        )
        assert j1 is not None
        s.commit()
    with fac() as s:
        j2 = claim_next_eligible_refiner_job(
            s,
            lease_owner="w2",
            lease_expires_at=t0 + timedelta(hours=1),
            now=t0,
        )
        assert j2 is None
        s.commit()


def test_expired_lease_can_be_reclaimed(session_factory):
    fac = session_factory
    t0 = _t0()
    with fac() as s:
        refiner_enqueue_or_get_job(s, dedupe_key="reclaim", job_kind="test")
        s.commit()
    with fac() as s:
        j = claim_next_eligible_refiner_job(
            s,
            lease_owner="w1",
            lease_expires_at=t0 + timedelta(seconds=30),
            now=t0,
        )
        assert j is not None
        assert j.attempt_count == 1
        s.commit()
        jid = j.id
    with fac() as s:
        j2 = claim_next_eligible_refiner_job(
            s,
            lease_owner="w2",
            lease_expires_at=t0 + timedelta(hours=1),
            now=t0 + timedelta(minutes=5),
        )
        assert j2 is not None
        assert j2.id == jid
        assert j2.lease_owner == "w2"
        assert j2.attempt_count == 2
        s.commit()


def test_complete_only_succeeds_for_owning_lease(session_factory):
    fac = session_factory
    t0 = _t0()
    with fac() as s:
        refiner_enqueue_or_get_job(s, dedupe_key="done", job_kind="test")
        s.commit()
    with fac() as s:
        j = claim_next_eligible_refiner_job(
            s,
            lease_owner="good",
            lease_expires_at=t0 + timedelta(hours=1),
            now=t0,
        )
        jid = j.id
        s.commit()
    with fac() as s:
        assert not complete_claimed_refiner_job(
            s,
            job_id=jid,
            lease_owner="evil",
            now=t0,
        )
        s.rollback()
    with fac() as s:
        assert complete_claimed_refiner_job(
            s,
            job_id=jid,
            lease_owner="good",
            now=t0,
        )
        s.commit()
    with fac() as s:
        row = s.get(RefinerJob, jid)
        assert row.status == RefinerJobStatus.COMPLETED.value


def test_complete_fails_when_lease_expired(session_factory):
    fac = session_factory
    t0 = _t0()
    with fac() as s:
        refiner_enqueue_or_get_job(s, dedupe_key="late", job_kind="test")
        s.commit()
    with fac() as s:
        j = claim_next_eligible_refiner_job(
            s,
            lease_owner="w",
            lease_expires_at=t0 + timedelta(seconds=10),
            now=t0,
        )
        jid = j.id
        s.commit()
    with fac() as s:
        assert not complete_claimed_refiner_job(
            s,
            job_id=jid,
            lease_owner="w",
            now=t0 + timedelta(minutes=30),
        )
        s.rollback()


def test_fail_requeues_until_max_attempts_then_failed(session_factory):
    fac = session_factory
    t0 = _t0()
    with fac() as s:
        refiner_enqueue_or_get_job(
            s,
            dedupe_key="retry",
            job_kind="test",
            max_attempts=2,
        )
        s.commit()

    for round_i in range(2):
        with fac() as s:
            j = claim_next_eligible_refiner_job(
                s,
                lease_owner="w",
                lease_expires_at=t0 + timedelta(hours=1),
                now=t0,
            )
            assert j is not None
            assert j.attempt_count == round_i + 1
            jid = j.id
            ok = fail_claimed_refiner_job(
                s,
                job_id=jid,
                lease_owner="w",
                error_message=f"e{round_i}",
                now=t0,
            )
            assert ok
            s.commit()

    with fac() as s:
        j = claim_next_eligible_refiner_job(
            s,
            lease_owner="w",
            lease_expires_at=t0 + timedelta(hours=1),
            now=t0,
        )
        assert j is None
        row = s.get(RefinerJob, jid)
        assert row.status == RefinerJobStatus.FAILED.value
        assert row.last_error == "e1"


def test_fail_leased_after_complete_failure_sets_handler_ok_finalize_failed(session_factory):
    fac = session_factory
    t0 = _t0()
    with fac() as s:
        refiner_enqueue_or_get_job(s, dedupe_key="term-fail", job_kind="test")
        s.commit()
    with fac() as s:
        j = claim_next_eligible_refiner_job(
            s,
            lease_owner="w",
            lease_expires_at=t0 + timedelta(hours=1),
            now=t0,
        )
        assert j is not None
        assert j.attempt_count == 1
        jid = j.id
        s.commit()
    with fac() as s:
        assert fail_leased_refiner_job_after_complete_failure(
            s,
            job_id=jid,
            lease_owner="w",
            error_message="refiner_terminalization_failure: synthetic",
            now=t0,
        )
        s.commit()
    with fac() as s:
        row = s.get(RefinerJob, jid)
        assert row.status == RefinerJobStatus.HANDLER_OK_FINALIZE_FAILED.value
        assert row.attempt_count == 1
        assert row.lease_owner is None
        assert "synthetic" in (row.last_error or "")
    with fac() as s:
        assert (
            claim_next_eligible_refiner_job(
                s,
                lease_owner="w2",
                lease_expires_at=t0 + timedelta(hours=1),
                now=t0,
            )
            is None
        )


def test_handler_ok_finalize_failed_row_is_not_claimable(session_factory):
    fac = session_factory
    t0 = _t0()
    with fac() as s:
        refiner_enqueue_or_get_job(s, dedupe_key="finalize-stuck", job_kind="test")
        s.commit()
    with fac() as s:
        row = s.get(RefinerJob, 1)
        assert row is not None
        row.status = RefinerJobStatus.HANDLER_OK_FINALIZE_FAILED.value
        row.lease_owner = None
        row.lease_expires_at = None
        s.commit()
    with fac() as s:
        assert (
            claim_next_eligible_refiner_job(
                s,
                lease_owner="w",
                lease_expires_at=t0 + timedelta(hours=1),
                now=t0,
            )
            is None
        )


def test_fail_leased_after_complete_failure_rejects_wrong_owner(session_factory):
    fac = session_factory
    t0 = _t0()
    with fac() as s:
        refiner_enqueue_or_get_job(s, dedupe_key="term-owner", job_kind="test")
        s.commit()
    with fac() as s:
        j = claim_next_eligible_refiner_job(
            s,
            lease_owner="good",
            lease_expires_at=t0 + timedelta(hours=1),
            now=t0,
        )
        jid = j.id
        s.commit()
    with fac() as s:
        assert not fail_leased_refiner_job_after_complete_failure(
            s,
            job_id=jid,
            lease_owner="evil",
            error_message="x",
            now=t0,
        )
        s.rollback()


def test_recover_handler_ok_finalize_failed_to_completed(session_factory):
    fac = session_factory
    t0 = _t0()
    with fac() as s:
        refiner_enqueue_or_get_job(s, dedupe_key="recover-ok", job_kind="test")
        s.commit()
    with fac() as s:
        j = claim_next_eligible_refiner_job(
            s,
            lease_owner="w",
            lease_expires_at=t0 + timedelta(hours=1),
            now=t0,
        )
        jid = j.id
        fail_leased_refiner_job_after_complete_failure(
            s,
            job_id=jid,
            lease_owner="w",
            error_message="refiner_terminalization_failure: synthetic",
            now=t0,
        )
        s.commit()
    with fac() as s:
        assert (
            recover_handler_ok_finalize_failed_to_completed(
                s,
                job_id=jid,
                recovered_by_label="tester",
                now=t0,
            )
            == "ok"
        )
        s.commit()
    with fac() as s:
        row = s.get(RefinerJob, jid)
        assert row.status == RefinerJobStatus.COMPLETED.value
        assert "manual_recover_finalize_failure" in (row.last_error or "")
        assert "refiner_terminalization_failure" in (row.last_error or "")
        assert row.lease_owner is None


def test_recover_finalize_rejects_wrong_status(session_factory):
    fac = session_factory
    t0 = _t0()
    with fac() as s:
        refiner_enqueue_or_get_job(s, dedupe_key="recover-wrong", job_kind="test")
        s.commit()
    with fac() as s:
        j = claim_next_eligible_refiner_job(
            s,
            lease_owner="w",
            lease_expires_at=t0 + timedelta(hours=1),
            now=t0,
        )
        jid = j.id
        s.commit()
    with fac() as s:
        assert (
            recover_handler_ok_finalize_failed_to_completed(
                s,
                job_id=jid,
                recovered_by_label="x",
                now=t0,
            )
            == "wrong_status"
        )
        s.rollback()


def test_recover_finalize_rejects_missing_job(session_factory):
    fac = session_factory
    with fac() as s:
        assert (
            recover_handler_ok_finalize_failed_to_completed(
                s,
                job_id=99999,
                recovered_by_label="x",
            )
            == "not_found"
        )


def test_two_workers_claim_different_jobs(session_factory):
    fac = session_factory
    t0 = _t0()
    with fac() as s:
        refiner_enqueue_or_get_job(s, dedupe_key="a", job_kind="test")
        refiner_enqueue_or_get_job(s, dedupe_key="b", job_kind="test")
        s.commit()

    barrier = threading.Barrier(2)
    claimed: list[int | None] = []

    def work():
        barrier.wait()
        with fac() as s:
            j = claim_next_eligible_refiner_job(
                s,
                lease_owner=threading.current_thread().name,
                lease_expires_at=t0 + timedelta(hours=1),
                now=t0,
            )
            s.commit()
            claimed.append(j.id if j else None)

    t1 = threading.Thread(target=work, name="t1")
    t2 = threading.Thread(target=work, name="t2")
    t1.start()
    t2.start()
    t1.join()
    t2.join()
    ids = {x for x in claimed if x is not None}
    assert len(ids) == 2
