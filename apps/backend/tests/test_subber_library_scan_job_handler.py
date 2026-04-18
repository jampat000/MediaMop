"""Tests for ``subber.library_scan.*.v1`` handlers."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from mediamop.core.config import MediaMopSettings
from mediamop.core.db import Base
from mediamop.modules.subber.subber_job_handlers import build_subber_job_handlers
from mediamop.modules.subber.subber_job_kinds import SUBBER_JOB_KIND_LIBRARY_SCAN_TV
from mediamop.modules.subber.subber_jobs_model import SubberJob
from mediamop.modules.subber.subber_jobs_ops import subber_enqueue_or_get_job
from mediamop.modules.subber.subber_settings_model import SubberSettingsRow
from mediamop.modules.subber.subber_subtitle_state_model import SubberSubtitleState
from mediamop.modules.subber.worker_loop import process_one_subber_job

import mediamop.modules.subber.subber_jobs_model  # noqa: F401
import mediamop.modules.subber.subber_settings_model  # noqa: F401
import mediamop.modules.subber.subber_subtitle_state_model  # noqa: F401
import mediamop.platform.activity.models  # noqa: F401
import mediamop.platform.auth.models  # noqa: F401


@pytest.fixture
def session_factory(tmp_path: Path):
    url = f"sqlite:///{tmp_path / 'lib_scan.sqlite'}"
    engine = create_engine(url, connect_args={"check_same_thread": False}, future=True)
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, class_=Session, autoflush=False, autocommit=False, future=True)


def test_library_scan_enqueues_missing_not_recent(session_factory) -> None:
    with session_factory() as s:
        s.add(SubberSettingsRow(id=1, enabled=True))
        s.add(
            SubberSubtitleState(
                media_scope="tv",
                file_path="/v/m1.mkv",
                language_code="en",
                status="missing",
                last_searched_at=None,
            ),
        )
        s.commit()
        subber_enqueue_or_get_job(
            s,
            dedupe_key="lib:tv:1",
            job_kind=SUBBER_JOB_KIND_LIBRARY_SCAN_TV,
            payload_json=json.dumps({"media_scope": "tv"}),
        )
        s.commit()

    settings = MediaMopSettings.load()
    handlers = build_subber_job_handlers(settings, session_factory)
    t0 = datetime(2026, 6, 1, 12, 0, 0, tzinfo=timezone.utc)
    process_one_subber_job(session_factory, lease_owner="ls1", job_handlers=handlers, now=t0, lease_seconds=600)
    with session_factory() as s:
        jobs = list(s.scalars(select(SubberJob).order_by(SubberJob.id.asc())).all())
        assert len(jobs) == 2
        assert jobs[1].job_kind.endswith("subtitle_search.tv.v1")


def test_library_scan_skips_recently_searched(session_factory) -> None:
    recent = datetime(2026, 6, 1, 11, 0, 0, tzinfo=timezone.utc)
    with session_factory() as s:
        s.add(SubberSettingsRow(id=1, enabled=True))
        s.add(
            SubberSubtitleState(
                media_scope="tv",
                file_path="/v/m2.mkv",
                language_code="en",
                status="missing",
                last_searched_at=recent,
            ),
        )
        s.commit()
        subber_enqueue_or_get_job(
            s,
            dedupe_key="lib:tv:2",
            job_kind=SUBBER_JOB_KIND_LIBRARY_SCAN_TV,
            payload_json=json.dumps({"media_scope": "tv"}),
        )
        s.commit()

    settings = MediaMopSettings.load()
    handlers = build_subber_job_handlers(settings, session_factory)
    t0 = datetime(2026, 6, 1, 12, 0, 0, tzinfo=timezone.utc)
    process_one_subber_job(session_factory, lease_owner="ls2", job_handlers=handlers, now=t0, lease_seconds=600)
    with session_factory() as s:
        jobs = list(s.scalars(select(SubberJob)).all())
        assert len(jobs) == 1
