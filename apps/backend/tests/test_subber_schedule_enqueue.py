"""Unit tests for ``subber_schedule_enqueue`` — TV, Movies, and upgrade schedules enqueue independently."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from mediamop.core.db import Base
from mediamop.modules.subber.subber_job_kinds import (
    SUBBER_JOB_KIND_LIBRARY_SCAN_MOVIES,
    SUBBER_JOB_KIND_LIBRARY_SCAN_TV,
    SUBBER_JOB_KIND_SUBTITLE_UPGRADE,
)
from mediamop.modules.subber.subber_jobs_model import SubberJob
import mediamop.modules.subber.subber_jobs_model  # noqa: F401
from mediamop.modules.subber.subber_schedule_enqueue import (
    enqueue_due_subber_movies_scan,
    enqueue_due_subber_tv_scan,
    enqueue_due_subber_upgrade,
)
from mediamop.modules.subber.subber_settings_service import ensure_subber_settings_row
import mediamop.modules.subber.subber_settings_model  # noqa: F401
import mediamop.platform.auth.models  # noqa: F401


@pytest.fixture
def session_factory(tmp_path: Path):
    url = f"sqlite:///{tmp_path / 'subber_sched.sqlite'}"
    engine = create_engine(url, connect_args={"check_same_thread": False}, future=True)
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, class_=Session, autoflush=False, autocommit=False, future=True)


def _job_kinds(session_factory) -> list[str]:
    with session_factory() as s:
        rows = list(s.scalars(select(SubberJob).order_by(SubberJob.id.asc())).all())
        return [str(r.job_kind) for r in rows]


def test_tv_scan_fires_when_enabled(session_factory) -> None:
    t0 = datetime(2026, 4, 1, 12, 0, 0, tzinfo=timezone.utc)
    with session_factory() as s:
        with s.begin():
            row = ensure_subber_settings_row(s)
            row.enabled = True
            row.tv_schedule_enabled = True
            row.tv_schedule_interval_seconds = 60
            row.tv_last_scheduled_scan_enqueued_at = None
            row.tv_schedule_hours_limited = False
            n = enqueue_due_subber_tv_scan(s, now=t0)
        assert n == 1
    kinds = _job_kinds(session_factory)
    assert SUBBER_JOB_KIND_LIBRARY_SCAN_TV in kinds


def test_tv_scan_does_not_fire_when_disabled(session_factory) -> None:
    t0 = datetime(2026, 4, 1, 12, 0, 0, tzinfo=timezone.utc)
    with session_factory() as s:
        with s.begin():
            row = ensure_subber_settings_row(s)
            row.enabled = True
            row.tv_schedule_enabled = False
            row.tv_schedule_interval_seconds = 60
            row.tv_last_scheduled_scan_enqueued_at = None
            n = enqueue_due_subber_tv_scan(s, now=t0)
        assert n == 0
    assert _job_kinds(session_factory) == []


def test_tv_scan_does_not_fire_before_interval(session_factory) -> None:
    t0 = datetime(2026, 4, 1, 12, 0, 0, tzinfo=timezone.utc)
    last = t0 - timedelta(seconds=30)
    with session_factory() as s:
        with s.begin():
            row = ensure_subber_settings_row(s)
            row.enabled = True
            row.tv_schedule_enabled = True
            row.tv_schedule_interval_seconds = 3600
            row.tv_last_scheduled_scan_enqueued_at = last
            row.tv_schedule_hours_limited = False
            n = enqueue_due_subber_tv_scan(s, now=t0)
        assert n == 0
    assert _job_kinds(session_factory) == []


def test_movies_scan_fires_independently_of_tv(session_factory) -> None:
    t0 = datetime(2026, 4, 1, 12, 0, 0, tzinfo=timezone.utc)
    with session_factory() as s:
        with s.begin():
            row = ensure_subber_settings_row(s)
            row.enabled = True
            row.tv_schedule_enabled = False
            row.movies_schedule_enabled = True
            row.movies_schedule_interval_seconds = 60
            row.movies_last_scheduled_scan_enqueued_at = None
            row.movies_schedule_hours_limited = False
            assert enqueue_due_subber_tv_scan(s, now=t0) == 0
            assert enqueue_due_subber_movies_scan(s, now=t0) == 1
    kinds = _job_kinds(session_factory)
    assert kinds == [SUBBER_JOB_KIND_LIBRARY_SCAN_MOVIES]


def test_upgrade_scan_fires_when_both_flags_enabled(session_factory) -> None:
    t0 = datetime(2026, 4, 1, 12, 0, 0, tzinfo=timezone.utc)
    with session_factory() as s:
        with s.begin():
            row = ensure_subber_settings_row(s)
            row.enabled = True
            row.upgrade_enabled = True
            row.upgrade_schedule_enabled = True
            row.upgrade_schedule_interval_seconds = 60
            row.upgrade_last_scheduled_at = None
            row.upgrade_schedule_hours_limited = False
            n = enqueue_due_subber_upgrade(s, now=t0)
        assert n == 1
    kinds = _job_kinds(session_factory)
    assert SUBBER_JOB_KIND_SUBTITLE_UPGRADE in kinds


def test_upgrade_scan_does_not_fire_when_upgrade_disabled(session_factory) -> None:
    t0 = datetime(2026, 4, 1, 12, 0, 0, tzinfo=timezone.utc)
    with session_factory() as s:
        with s.begin():
            row = ensure_subber_settings_row(s)
            row.enabled = True
            row.upgrade_enabled = False
            row.upgrade_schedule_enabled = True
            row.upgrade_schedule_interval_seconds = 60
            row.upgrade_last_scheduled_at = None
            row.upgrade_schedule_hours_limited = False
            n = enqueue_due_subber_upgrade(s, now=t0)
        assert n == 0
    assert _job_kinds(session_factory) == []


def test_upgrade_scan_does_not_fire_when_schedule_disabled(session_factory) -> None:
    t0 = datetime(2026, 4, 1, 12, 0, 0, tzinfo=timezone.utc)
    with session_factory() as s:
        with s.begin():
            row = ensure_subber_settings_row(s)
            row.enabled = True
            row.upgrade_enabled = True
            row.upgrade_schedule_enabled = False
            row.upgrade_schedule_interval_seconds = 60
            row.upgrade_last_scheduled_at = None
            row.upgrade_schedule_hours_limited = False
            n = enqueue_due_subber_upgrade(s, now=t0)
        assert n == 0
    assert _job_kinds(session_factory) == []


@patch(
    "mediamop.modules.subber.subber_schedule_enqueue.enqueue_due_subber_tv_scan",
    side_effect=RuntimeError("tv tick failed"),
)
def test_tv_crash_does_not_affect_movies_enqueue(mock_tv: object, session_factory) -> None:
    t0 = datetime(2026, 4, 1, 12, 0, 0, tzinfo=timezone.utc)
    with session_factory() as s:
        with s.begin():
            row = ensure_subber_settings_row(s)
            row.enabled = True
            row.tv_schedule_enabled = False
            row.movies_schedule_enabled = True
            row.movies_schedule_interval_seconds = 60
            row.movies_last_scheduled_scan_enqueued_at = None
            row.movies_schedule_hours_limited = False
            assert enqueue_due_subber_movies_scan(s, now=t0) == 1
    assert mock_tv.call_count == 0
    kinds = _job_kinds(session_factory)
    assert kinds == [SUBBER_JOB_KIND_LIBRARY_SCAN_MOVIES]
