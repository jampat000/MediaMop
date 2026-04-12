"""Refiner candidate gate: refiner_jobs, handler wiring, mocked live queue (no Fetcher lane)."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from mediamop.core.config import MediaMopSettings
from mediamop.core.db import Base
from mediamop.modules.refiner.jobs_model import RefinerJob, RefinerJobStatus
from mediamop.modules.refiner.jobs_ops import refiner_enqueue_or_get_job
from mediamop.modules.refiner.refiner_candidate_gate_job_kinds import REFINER_CANDIDATE_GATE_JOB_KIND
from mediamop.modules.refiner.refiner_job_handlers import build_refiner_job_handlers
from mediamop.modules.refiner.worker_loop import process_one_refiner_job
from mediamop.platform.activity import constants as C
from mediamop.platform.activity.models import ActivityEvent

import mediamop.modules.refiner.jobs_model  # noqa: F401
import mediamop.platform.activity.models  # noqa: F401
import mediamop.platform.auth.models  # noqa: F401


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


def test_candidate_gate_handler_uses_live_queue_shape_not_fetcher_jobs(
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

    def _fake_fetch(**_kwargs):
        return fake_rows

    t0 = datetime(2026, 4, 12, 12, 0, 0, tzinfo=timezone.utc)
    payload = {
        "target": "radarr",
        "release_title": "Gate Test",
        "release_year": 2001,
        "output_path": "/q/m.mkv",
        "movie_id": None,
        "series_id": None,
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
        "mediamop.modules.refiner.refiner_candidate_gate_handlers.fetch_arr_v3_queue_rows",
        side_effect=_fake_fetch,
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


def test_refiner_candidate_gate_queue_fetch_module_does_not_import_fetcher() -> None:
    import mediamop.modules.refiner.refiner_candidate_gate_queue_fetch as mod

    src = Path(mod.__file__).read_text(encoding="utf-8")
    assert "mediamop.modules.fetcher" not in src
