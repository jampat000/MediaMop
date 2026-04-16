"""Refiner supplied payload evaluation: refiner_jobs lane, refiner.* namespace, timing isolation."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from mediamop.core.config import MediaMopSettings
from mediamop.core.db import Base
from mediamop.modules.refiner.jobs_model import RefinerJob, RefinerJobStatus
from mediamop.modules.refiner.jobs_ops import refiner_enqueue_or_get_job
from mediamop.modules.refiner.refiner_candidate_gate_job_kinds import REFINER_CANDIDATE_GATE_JOB_KIND
from mediamop.modules.refiner.refiner_file_remux_pass_job_kinds import REFINER_FILE_REMUX_PASS_JOB_KIND
from mediamop.modules.refiner.refiner_job_handlers import build_refiner_job_handlers
from mediamop.modules.refiner.refiner_watched_folder_remux_scan_dispatch_job_kinds import (
    REFINER_WATCHED_FOLDER_REMUX_SCAN_DISPATCH_JOB_KIND,
)
from mediamop.modules.refiner.refiner_supplied_payload_evaluation_job_kinds import (
    REFINER_SUPPLIED_PAYLOAD_EVALUATION_JOB_KIND,
)
from mediamop.modules.refiner.refiner_work_temp_stale_sweep_job_kinds import (
    REFINER_WORK_TEMP_STALE_SWEEP_JOB_KIND,
)
from mediamop.modules.refiner.worker_loop import process_one_refiner_job
from mediamop.platform.activity import constants as C
from mediamop.platform.activity.models import ActivityEvent

import mediamop.modules.refiner.jobs_model  # noqa: F401
import mediamop.platform.activity.models  # noqa: F401
import mediamop.platform.auth.models  # noqa: F401


@pytest.fixture
def jobs_engine(tmp_path: Path):
    url = f"sqlite:///{tmp_path / 'refiner_payload_eval_lane.sqlite'}"
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


def test_build_refiner_job_handlers_registry_is_refiner_prefixed_only(session_factory) -> None:
    settings = MediaMopSettings.load()
    reg = build_refiner_job_handlers(settings, session_factory)
    assert set(reg) == {
        REFINER_SUPPLIED_PAYLOAD_EVALUATION_JOB_KIND,
        REFINER_CANDIDATE_GATE_JOB_KIND,
        REFINER_FILE_REMUX_PASS_JOB_KIND,
        REFINER_WATCHED_FOLDER_REMUX_SCAN_DISPATCH_JOB_KIND,
        REFINER_WORK_TEMP_STALE_SWEEP_JOB_KIND,
    }
    assert all(k.startswith("refiner.") for k in reg)


def test_supplied_payload_evaluation_runs_on_refiner_lane_records_activity(session_factory) -> None:
    t0 = datetime(2026, 4, 11, 12, 0, 0, tzinfo=timezone.utc)
    payload = {
        "rows": [
            {
                "applies_to_file": True,
                "is_upstream_active": False,
                "is_import_pending": True,
                "blocking_suppressed_for_import_wait": False,
                "queue_title": None,
                "queue_year": None,
            },
        ],
        "file": {"title": "ignored.for.applies", "year": 2020},
    }
    with session_factory() as s:
        refiner_enqueue_or_get_job(
            s,
            dedupe_key="test:supplied-payload-evaluation:lane",
            job_kind=REFINER_SUPPLIED_PAYLOAD_EVALUATION_JOB_KIND,
            payload_json=json.dumps(payload),
        )
        s.commit()

    settings = MediaMopSettings.load()
    handlers = build_refiner_job_handlers(settings, session_factory)
    assert (
        process_one_refiner_job(
            session_factory,
            lease_owner="lane-test",
            job_handlers=handlers,
            now=t0,
            lease_seconds=3600,
        )
        == "processed"
    )

    with session_factory() as s:
        job = s.get(RefinerJob, 1)
        assert job is not None
        assert job.status == RefinerJobStatus.COMPLETED.value
        ev = s.scalars(
            select(ActivityEvent).where(
                ActivityEvent.event_type == C.REFINER_SUPPLIED_PAYLOAD_EVALUATION_COMPLETED,
            ),
        ).first()
        assert ev is not None
        assert ev.module == "refiner"
        body = json.loads(ev.detail or "{}")
        assert body.get("owned") is True
        assert body.get("blocked_upstream") is False


def test_refiner_supplied_payload_evaluation_schedule_settings_independent_from_fetcher(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MEDIAMOP_REFINER_SUPPLIED_PAYLOAD_EVALUATION_SCHEDULE_INTERVAL_SECONDS", "3333")
    monkeypatch.setenv("MEDIAMOP_FETCHER_SONARR_MISSING_SEARCH_SCHEDULE_INTERVAL_SECONDS", "4444")
    s = MediaMopSettings.load()
    assert s.refiner_supplied_payload_evaluation_schedule_interval_seconds == 3333
    assert s.fetcher_sonarr_missing_search_schedule_interval_seconds == 4444


def test_legacy_library_audit_pass_schedule_env_still_sets_interval(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MEDIAMOP_REFINER_SUPPLIED_PAYLOAD_EVALUATION_SCHEDULE_INTERVAL_SECONDS", raising=False)
    monkeypatch.setenv("MEDIAMOP_REFINER_LIBRARY_AUDIT_PASS_SCHEDULE_INTERVAL_SECONDS", "3120")
    s = MediaMopSettings.load()
    assert s.refiner_supplied_payload_evaluation_schedule_interval_seconds == 3120


def test_refiner_supplied_payload_evaluation_periodic_module_does_not_import_fetcher() -> None:
    import mediamop.modules.refiner.refiner_supplied_payload_evaluation_periodic_enqueue as mod

    src = Path(mod.__file__).read_text(encoding="utf-8")
    assert "mediamop.modules.fetcher" not in src
