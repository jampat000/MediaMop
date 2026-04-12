"""Trimmer durable lane: trimmer_jobs, trimmer.* namespace, worker dispatch."""

from __future__ import annotations

import json
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from mediamop.core.config import MediaMopSettings
from mediamop.core.db import Base
from mediamop.modules.queue_worker.job_kind_boundaries import (
    validate_trimmer_worker_handler_registry,
)
from mediamop.modules.trimmer.trimmer_job_handlers import build_trimmer_job_handlers
from mediamop.modules.trimmer.trimmer_jobs_model import TrimmerJob, TrimmerJobStatus
from mediamop.modules.trimmer.trimmer_jobs_ops import trimmer_enqueue_or_get_job
from mediamop.modules.trimmer.trimmer_supplied_trim_plan_json_file_write_job_kinds import (
    TRIMMER_SUPPLIED_TRIM_PLAN_JSON_FILE_WRITE_JOB_KIND,
)
from mediamop.modules.trimmer.trimmer_supplied_trim_plan_json_file_write_paths import (
    trimmer_plan_exports_dir,
)
from mediamop.modules.trimmer.trimmer_trim_plan_constraints_check_job_kinds import (
    TRIMMER_TRIM_PLAN_CONSTRAINTS_CHECK_JOB_KIND,
)
from mediamop.modules.trimmer.worker_loop import process_one_trimmer_job
from mediamop.platform.activity import constants as C
from mediamop.platform.activity.models import ActivityEvent

import mediamop.modules.trimmer.trimmer_jobs_model  # noqa: F401
import mediamop.platform.activity.models  # noqa: F401
import mediamop.platform.auth.models  # noqa: F401


@pytest.fixture
def jobs_engine(tmp_path: Path):
    url = f"sqlite:///{tmp_path / 'trimmer_lane.sqlite'}"
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


@pytest.fixture
def trimmer_settings(tmp_path: Path) -> MediaMopSettings:
    return replace(MediaMopSettings.load(), mediamop_home=str(tmp_path / "mmhome"))


def test_build_trimmer_job_handlers_registry_is_trimmer_prefixed_only(
    session_factory,
    trimmer_settings: MediaMopSettings,
) -> None:
    reg = build_trimmer_job_handlers(trimmer_settings, session_factory)
    assert set(reg) == {
        TRIMMER_TRIM_PLAN_CONSTRAINTS_CHECK_JOB_KIND,
        TRIMMER_SUPPLIED_TRIM_PLAN_JSON_FILE_WRITE_JOB_KIND,
    }
    assert all(k.startswith("trimmer.") for k in reg)
    validate_trimmer_worker_handler_registry(reg)


def test_trim_plan_constraints_check_runs_on_trimmer_lane_records_activity(
    session_factory,
    trimmer_settings: MediaMopSettings,
) -> None:
    t0 = datetime(2026, 4, 11, 12, 0, 0, tzinfo=timezone.utc)
    payload = {"segments": [{"start_sec": 0, "end_sec": 30}], "source_duration_sec": 120}
    with session_factory() as s:
        trimmer_enqueue_or_get_job(
            s,
            dedupe_key="test:trimmer:lane:1",
            job_kind=TRIMMER_TRIM_PLAN_CONSTRAINTS_CHECK_JOB_KIND,
            payload_json=json.dumps(payload),
        )
        s.commit()

    handlers = build_trimmer_job_handlers(trimmer_settings, session_factory)
    assert (
        process_one_trimmer_job(
            session_factory,
            lease_owner="lane-test",
            job_handlers=handlers,
            now=t0,
            lease_seconds=3600,
        )
        == "processed"
    )

    with session_factory() as s:
        job = s.get(TrimmerJob, 1)
        assert job is not None
        assert job.status == TrimmerJobStatus.COMPLETED.value
        ev = s.scalars(
            select(ActivityEvent).where(
                ActivityEvent.event_type == C.TRIMMER_TRIM_PLAN_CONSTRAINTS_CHECK_COMPLETED,
            ),
        ).first()
        assert ev is not None
        assert ev.module == "trimmer"
        body = json.loads(ev.detail or "{}")
        assert body.get("ok") is True


def test_supplied_trim_plan_json_file_write_writes_under_plan_exports(
    session_factory,
    trimmer_settings: MediaMopSettings,
) -> None:
    t0 = datetime(2026, 4, 11, 12, 0, 0, tzinfo=timezone.utc)
    payload = {"segments": [{"start_sec": 0, "end_sec": 10}, {"start_sec": 10, "end_sec": 20}]}
    with session_factory() as s:
        trimmer_enqueue_or_get_job(
            s,
            dedupe_key="test:trimmer:lane:json-write",
            job_kind=TRIMMER_SUPPLIED_TRIM_PLAN_JSON_FILE_WRITE_JOB_KIND,
            payload_json=json.dumps(payload),
        )
        s.commit()

    handlers = build_trimmer_job_handlers(trimmer_settings, session_factory)
    assert (
        process_one_trimmer_job(
            session_factory,
            lease_owner="lane-json",
            job_handlers=handlers,
            now=t0,
            lease_seconds=3600,
        )
        == "processed"
    )

    outbox = trimmer_plan_exports_dir(trimmer_settings.mediamop_home)
    files = list(outbox.glob("trimmer-plan-job-*.json"))
    assert len(files) == 1
    written = json.loads(files[0].read_text(encoding="utf-8"))
    assert written["schema_kind"] == TRIMMER_SUPPLIED_TRIM_PLAN_JSON_FILE_WRITE_JOB_KIND
    assert len(written["segments"]) == 2

    with session_factory() as s:
        job = s.get(TrimmerJob, 1)
        assert job is not None
        assert job.status == TrimmerJobStatus.COMPLETED.value
        ev = s.scalars(
            select(ActivityEvent).where(
                ActivityEvent.event_type == C.TRIMMER_SUPPLIED_TRIM_PLAN_JSON_FILE_WRITE_COMPLETED,
            ),
        ).first()
        assert ev is not None
        detail = json.loads(ev.detail or "{}")
        assert detail.get("ok") is True
        assert "output_relative_path" in detail
