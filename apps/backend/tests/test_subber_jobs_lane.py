"""Subber durable lane: subber_jobs, subber.* namespace, worker dispatch."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from mediamop.core.db import Base
from mediamop.modules.queue_worker.job_kind_boundaries import validate_subber_worker_handler_registry
from mediamop.modules.subber.subber_job_handlers import build_subber_job_handlers
from mediamop.modules.subber.subber_jobs_model import SubberJob, SubberJobStatus
from mediamop.modules.subber.subber_jobs_ops import subber_enqueue_or_get_job
from mediamop.modules.subber.subber_supplied_cue_timeline_constraints_check_job_kinds import (
    SUBBER_SUPPLIED_CUE_TIMELINE_CONSTRAINTS_CHECK_JOB_KIND,
)
from mediamop.modules.subber.worker_loop import process_one_subber_job
from mediamop.platform.activity import constants as C
from mediamop.platform.activity.models import ActivityEvent

import mediamop.modules.subber.subber_jobs_model  # noqa: F401
import mediamop.platform.activity.models  # noqa: F401
import mediamop.platform.auth.models  # noqa: F401


@pytest.fixture
def jobs_engine(tmp_path: Path):
    url = f"sqlite:///{tmp_path / 'subber_lane.sqlite'}"
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


def test_build_subber_job_handlers_registry_is_subber_prefixed_only(session_factory) -> None:
    reg = build_subber_job_handlers(session_factory)
    assert set(reg) == {SUBBER_SUPPLIED_CUE_TIMELINE_CONSTRAINTS_CHECK_JOB_KIND}
    assert all(k.startswith("subber.") for k in reg)
    validate_subber_worker_handler_registry(reg)


def test_cue_timeline_constraints_check_runs_on_subber_lane_records_activity(session_factory) -> None:
    t0 = datetime(2026, 4, 11, 12, 0, 0, tzinfo=timezone.utc)
    payload = {"cues": [{"start_sec": 0, "end_sec": 30}], "source_duration_sec": 120}
    with session_factory() as s:
        subber_enqueue_or_get_job(
            s,
            dedupe_key="test:subber:lane:1",
            job_kind=SUBBER_SUPPLIED_CUE_TIMELINE_CONSTRAINTS_CHECK_JOB_KIND,
            payload_json=json.dumps(payload),
        )
        s.commit()

    handlers = build_subber_job_handlers(session_factory)
    assert (
        process_one_subber_job(
            session_factory,
            lease_owner="lane-test",
            job_handlers=handlers,
            now=t0,
            lease_seconds=3600,
        )
        == "processed"
    )

    with session_factory() as s:
        job = s.get(SubberJob, 1)
        assert job is not None
        assert job.status == SubberJobStatus.COMPLETED.value
        ev = s.scalars(
            select(ActivityEvent).where(
                ActivityEvent.event_type == C.SUBBER_SUPPLIED_CUE_TIMELINE_CONSTRAINTS_CHECK_COMPLETED,
            ),
        ).first()
        assert ev is not None
        assert ev.module == "subber"
        body = json.loads(ev.detail or "{}")
        assert body.get("ok") is True
