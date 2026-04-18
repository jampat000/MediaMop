"""Subber durable lane: subber_jobs, subber.* namespace, worker dispatch."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from mediamop.core.config import MediaMopSettings
from mediamop.core.db import Base
from mediamop.modules.queue_worker.job_kind_boundaries import validate_subber_worker_handler_registry
from mediamop.modules.subber.subber_job_handlers import build_subber_job_handlers
from mediamop.modules.subber.subber_job_kinds import (
    ALL_SUBBER_PRODUCTION_JOB_KINDS,
    SUBBER_JOB_KIND_SUBTITLE_SEARCH_TV,
    SUBBER_JOB_KIND_WEBHOOK_IMPORT_TV,
)
from mediamop.modules.subber.subber_jobs_model import SubberJob, SubberJobStatus
from mediamop.modules.subber.subber_jobs_ops import subber_enqueue_or_get_job
from mediamop.modules.subber.subber_settings_service import ensure_subber_settings_row
from mediamop.modules.subber.subber_subtitle_state_model import SubberSubtitleState
from mediamop.modules.subber.worker_loop import process_one_subber_job
from mediamop.platform.activity import constants as C
from mediamop.platform.activity.models import ActivityEvent

import mediamop.modules.subber.subber_jobs_model  # noqa: F401
import mediamop.modules.subber.subber_settings_model  # noqa: F401
import mediamop.modules.subber.subber_subtitle_state_model  # noqa: F401
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


def test_build_subber_job_handlers_registry_matches_production_kinds(session_factory) -> None:
    settings = MediaMopSettings.load()
    reg = build_subber_job_handlers(settings, session_factory)
    assert set(reg) == ALL_SUBBER_PRODUCTION_JOB_KINDS
    assert all(k.startswith("subber.") for k in reg)
    validate_subber_worker_handler_registry(reg)


def test_webhook_import_tv_runs_on_subber_lane_records_activity(session_factory) -> None:
    t0 = datetime(2026, 4, 11, 12, 0, 0, tzinfo=timezone.utc)
    settings = MediaMopSettings.load()
    payload = {
        "file_path": "/media/tv/Pilot.mkv",
        "media_scope": "tv",
        "title": "Breaking Bad",
        "year": None,
        "show_title": "Breaking Bad",
        "season_number": 1,
        "episode_number": 1,
        "episode_title": "Pilot",
        "sonarr_episode_id": 42,
        "radarr_movie_id": None,
    }
    with session_factory() as s:
        row = ensure_subber_settings_row(s)
        row.enabled = True
        s.commit()
    with session_factory() as s:
        subber_enqueue_or_get_job(
            s,
            dedupe_key="test:subber:lane:wh1",
            job_kind=SUBBER_JOB_KIND_WEBHOOK_IMPORT_TV,
            payload_json=json.dumps(payload),
        )
        s.commit()

    handlers = build_subber_job_handlers(settings, session_factory)
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
        jobs = list(s.scalars(select(SubberJob).order_by(SubberJob.id.asc())).all())
        assert len(jobs) == 2
        assert jobs[0].job_kind == SUBBER_JOB_KIND_WEBHOOK_IMPORT_TV
        assert jobs[0].status == SubberJobStatus.COMPLETED.value
        assert jobs[1].job_kind == SUBBER_JOB_KIND_SUBTITLE_SEARCH_TV
        assert jobs[1].status == SubberJobStatus.PENDING.value
        states = list(s.scalars(select(SubberSubtitleState)).all())
        assert len(states) == 1
        assert states[0].language_code == "en"
        ev = s.scalars(
            select(ActivityEvent).where(ActivityEvent.event_type == C.SUBBER_WEBHOOK_IMPORT_ENQUEUED),
        ).first()
        assert ev is not None
        assert ev.module == "subber"
