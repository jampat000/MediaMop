"""Refiner candidate gate: refiner_jobs, handler wiring, mocked media manager answers."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timezone
from pathlib import Path
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

import mediamop.modules.refiner.jobs_model  # noqa: F401
import mediamop.platform.activity.models  # noqa: F401
import mediamop.platform.auth.models  # noqa: F401
from mediamop.core.config import MediaMopSettings
from mediamop.core.db import Base
from mediamop.modules.refiner.jobs_model import RefinerJob, RefinerJobStatus
from mediamop.modules.refiner.jobs_ops import refiner_enqueue_or_get_job
from mediamop.modules.refiner.refiner_candidate_gate_job_kinds import REFINER_CANDIDATE_GATE_JOB_KIND
from mediamop.modules.refiner.refiner_job_handlers import build_refiner_job_handlers
from mediamop.modules.refiner.worker_loop import process_one_refiner_job
from mediamop.platform.activity import constants as C
from mediamop.platform.activity.models import ActivityEvent
from tests.manager_signal_helpers import reported, unreachable


@pytest.fixture
def jobs_engine(tmp_path: Path):
    url = f"sqlite:///{tmp_path / 'refiner_candidate_gate.sqlite'}"
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


def test_candidate_gate_handler_uses_live_queue_shape(
    session_factory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MEDIAMOP_ARR_RADARR_BASE_URL", "http://127.0.0.1:9")
    monkeypatch.setenv("MEDIAMOP_ARR_RADARR_API_KEY", "k")
    settings = MediaMopSettings.load()

    fake_rows = [
        {
            "status": "importPending",
            "outputPath": "/q/m.mkv",
            "movie": {"title": "Gate Test", "year": 2001},
        },
    ]

    t0 = datetime(2026, 4, 12, 12, 0, 0, tzinfo=UTC)
    payload = {
        "media_scope": "movie",
        "release_title": "Gate Test",
        "release_year": 2001,
        "output_path": "/q/m.mkv",
        "entity_id": None,
    }
    with session_factory() as s:
        refiner_enqueue_or_get_job(
            s,
            dedupe_key="refiner.candidate_gate.v1:test-lane",
            job_kind=REFINER_CANDIDATE_GATE_JOB_KIND,
            payload_json=json.dumps(payload),
        )
        s.commit()

    handlers = build_refiner_job_handlers(settings, session_factory)
    with patch(
        "mediamop.modules.refiner.refiner_candidate_gate_handlers.collect_queue_signals",
        return_value=(reported(fake_rows, name="Main"),),
    ):
        assert (
            process_one_refiner_job(
                session_factory,
                lease_owner="cg-test",
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
            select(ActivityEvent).where(ActivityEvent.event_type == C.REFINER_CANDIDATE_GATE_COMPLETED),
        ).first()
        assert ev is not None
        assert ev.module == "refiner"
        body = json.loads(ev.detail or "{}")
        assert body.get("verdict") == "proceed"


def test_candidate_gate_handler_reports_a_manager_it_could_not_reach(
    session_factory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An unreachable manager must not land in Activity as a clean, empty queue."""

    monkeypatch.delenv("MEDIAMOP_ARR_RADARR_BASE_URL", raising=False)
    monkeypatch.delenv("MEDIAMOP_ARR_RADARR_API_KEY", raising=False)
    settings = MediaMopSettings.load()

    payload = {
        "media_scope": "movie",
        "release_title": "Gate Test",
        "release_year": 2001,
        "output_path": "/q/m.mkv",
        "entity_id": None,
    }
    with session_factory() as s:
        refiner_enqueue_or_get_job(
            s,
            dedupe_key="refiner.candidate_gate.v1:unreachable",
            job_kind=REFINER_CANDIDATE_GATE_JOB_KIND,
            payload_json=json.dumps(payload),
        )
        s.commit()

    handlers = build_refiner_job_handlers(settings, session_factory)
    with patch(
        "mediamop.modules.refiner.refiner_candidate_gate_handlers.collect_queue_signals",
        return_value=(unreachable(name="4K", detail="Connection refused."),),
    ):
        assert (
            process_one_refiner_job(
                session_factory,
                lease_owner="cg-test",
                job_handlers=handlers,
                now=datetime(2026, 4, 12, 12, 0, 0, tzinfo=UTC),
                lease_seconds=3600,
            )
            == "processed"
        )

    with session_factory() as s:
        ev = s.scalars(
            select(ActivityEvent).where(ActivityEvent.event_type == C.REFINER_CANDIDATE_GATE_COMPLETED),
        ).first()
        assert ev is not None
        body = json.loads(ev.detail or "{}")
        assert body.get("verdict") == "no_upstream_signal"
        assert body.get("managers_without_queue_signal") == ["Radarr (4K)"]
