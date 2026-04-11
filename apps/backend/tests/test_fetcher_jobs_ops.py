"""Persisted fetcher_jobs queue — enqueue dedupe, atomic claim, complete, recover."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from mediamop.core.db import Base
from mediamop.modules.fetcher.fetcher_jobs_model import FetcherJob, FetcherJobStatus
from mediamop.modules.fetcher.fetcher_jobs_ops import (
    claim_next_eligible_fetcher_job,
    complete_claimed_fetcher_job,
    fail_leased_fetcher_job_after_complete_failure,
    fetcher_enqueue_or_get_job,
    recover_handler_ok_finalize_failed_to_completed,
)

import mediamop.modules.fetcher.fetcher_jobs_model  # noqa: F401
import mediamop.modules.refiner.jobs_model  # noqa: F401
import mediamop.platform.activity.models  # noqa: F401
import mediamop.platform.auth.models  # noqa: F401


@pytest.fixture
def jobs_engine(tmp_path):
    url = f"sqlite:///{tmp_path / 'fetcher_jobs.sqlite'}"
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


def test_fetcher_enqueue_duplicate_dedupe_returns_same_row(session_factory) -> None:
    with session_factory() as s:
        a = fetcher_enqueue_or_get_job(s, dedupe_key="fk1", job_kind="test")
        s.commit()
        aid = a.id
    with session_factory() as s:
        b = fetcher_enqueue_or_get_job(s, dedupe_key="fk1", job_kind="test")
        s.commit()
    assert b.id == aid


def test_fetcher_claim_complete_happy_path(session_factory) -> None:
    t0 = _t0()
    with session_factory() as s:
        fetcher_enqueue_or_get_job(s, dedupe_key="solo-f", job_kind="test")
        s.commit()
    with session_factory() as s:
        j = claim_next_eligible_fetcher_job(
            s,
            lease_owner="w1",
            lease_expires_at=t0 + timedelta(hours=1),
            now=t0,
        )
        assert j is not None
        jid = j.id
        s.commit()
    with session_factory() as s:
        assert complete_claimed_fetcher_job(s, job_id=jid, lease_owner="w1", now=t0)
        s.commit()
    with session_factory() as s:
        row = s.get(FetcherJob, jid)
        assert row is not None
        assert row.status == FetcherJobStatus.COMPLETED.value


def test_fetcher_recover_finalize_failed_to_completed(session_factory) -> None:
    t0 = _t0()
    with session_factory() as s:
        fetcher_enqueue_or_get_job(s, dedupe_key="rec-f", job_kind="test")
        s.commit()
    with session_factory() as s:
        j = claim_next_eligible_fetcher_job(
            s,
            lease_owner="w",
            lease_expires_at=t0 + timedelta(hours=1),
            now=t0,
        )
        jid = j.id
        fail_leased_fetcher_job_after_complete_failure(
            s,
            job_id=jid,
            lease_owner="w",
            error_message="fetcher_terminalization_failure: x",
            now=t0,
        )
        s.commit()
    with session_factory() as s:
        assert recover_handler_ok_finalize_failed_to_completed(s, job_id=jid, recovered_by_label="t") == "ok"
        s.commit()
    with session_factory() as s:
        row = s.get(FetcherJob, jid)
        assert row is not None
        assert row.status == FetcherJobStatus.COMPLETED.value
