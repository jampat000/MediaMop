"""A failed job leaves one plain Activity entry, and its words match what happens next (#488)."""

from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

import mediamop.modules.refiner.jobs_model  # noqa: F401
import mediamop.platform.activity.models  # noqa: F401
from mediamop.core.db import Base
from mediamop.modules.refiner.jobs_model import RefinerJob
from mediamop.modules.refiner.jobs_ops import refiner_enqueue_or_get_job
from mediamop.modules.refiner.refiner_file_remux_pass_activity import (
    record_refiner_file_processing_started,
    update_refiner_file_processing_progress,
)
from mediamop.modules.refiner.worker_loop import process_one_refiner_job
from mediamop.platform.activity import constants as C
from mediamop.platform.activity.models import ActivityEvent
from mediamop.platform.jobs.worker_failures import AlreadyRecordedFailure, refused_job_error

T0 = datetime(2026, 9, 17, 12, 0, 0, tzinfo=UTC)


@pytest.fixture
def factory(tmp_path) -> sessionmaker[Session]:  # type: ignore[no-untyped-def]
    engine = create_engine(
        f"sqlite:///{tmp_path / 'jobs.sqlite'}", connect_args={"check_same_thread": False}, future=True
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, class_=Session, expire_on_commit=False, future=True)


def _operator_part(error: str) -> str:
    return error.split(" Technical detail:")[0]


def test_a_refused_job_names_no_queue_kind_where_a_person_reads() -> None:
    error = refused_job_error(
        module="Refiner", technical_reason="refused job_kind 'trimmer.x.v1' (row id=4)", will_retry=False
    )
    assert "trimmer.x.v1" not in _operator_part(error)
    assert "trimmer.x.v1" in error
    assert "marked failed" in error


def test_a_failure_with_attempts_left_says_it_will_be_tried_again(factory) -> None:  # type: ignore[no-untyped-def]
    with factory() as s:
        refiner_enqueue_or_get_job(s, dedupe_key="a", job_kind="refiner.test.bad.v1", max_attempts=3)
        s.commit()

    def _boom(_ctx) -> None:  # type: ignore[no-untyped-def]
        raise RuntimeError("boom")

    process_one_refiner_job(factory, lease_owner="w", job_handlers={"refiner.test.bad.v1": _boom}, now=T0)
    with factory() as s:
        error = s.scalars(select(RefinerJob)).one().last_error or ""
    assert "try this job again shortly" in error
    assert "marked failed" not in error


def test_a_handler_that_recorded_its_own_failure_is_not_recorded_twice(factory) -> None:  # type: ignore[no-untyped-def]
    with factory() as s:
        refiner_enqueue_or_get_job(
            s,
            dedupe_key="b",
            job_kind="refiner.test.recorded.v1",
            payload_json=json.dumps({"relative_media_path": "a.mkv"}),
            max_attempts=1,
        )
        s.commit()

    def _already(_ctx) -> None:  # type: ignore[no-untyped-def]
        raise AlreadyRecordedFailure("the output folder is not writable")

    process_one_refiner_job(factory, lease_owner="w", job_handlers={"refiner.test.recorded.v1": _already}, now=T0)
    with factory() as s:
        assert s.scalars(select(ActivityEvent).where(ActivityEvent.event_type == C.REFINER_WORKER_FAILURE)).all() == []
        assert "marked failed" in (s.scalars(select(RefinerJob)).one().last_error or "")


def test_a_waiting_file_does_not_read_as_processing(factory) -> None:  # type: ignore[no-untyped-def]
    with factory() as s:
        activity_id = record_refiner_file_processing_started(
            s, payload={"job_id": 1, "relative_media_path": "Film/film.mkv", "status": "processing"}
        )
        update_refiner_file_processing_progress(
            s,
            activity_id=activity_id,
            payload={"job_id": 1, "relative_media_path": "Film/film.mkv", "status": "waiting"},
        )
        s.commit()
        assert s.get(ActivityEvent, activity_id).title == "Waiting to process film.mkv"  # type: ignore[union-attr]
