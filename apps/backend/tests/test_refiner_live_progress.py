"""Live progress is read from the pass's own activity row, never written twice (#463)."""

from __future__ import annotations

import json
from collections.abc import Iterator
from datetime import timedelta

import pytest
from sqlalchemy import delete
from sqlalchemy.orm import Session

from mediamop.core.config import MediaMopSettings
from mediamop.core.db import create_db_engine, create_session_factory
from mediamop.modules.refiner.refiner_live_progress import (
    STALE_AFTER,
    live_progress_by_path,
)
from mediamop.platform.activity import constants as activity_constants
from mediamop.platform.activity.models import ActivityEvent
from mediamop.platform.auth.sessions import utcnow

_PATH = "movies/Arrival.2016.2160p.mkv"


@pytest.fixture
def db_session() -> Iterator[Session]:
    settings = MediaMopSettings.load()
    factory = create_session_factory(create_db_engine(settings))
    with factory() as session:
        session.execute(delete(ActivityEvent))
        session.commit()
        yield session
        session.rollback()
        session.execute(delete(ActivityEvent))
        session.commit()


def _progress_row(
    session: Session,
    *,
    path: str = _PATH,
    status: str = "processing",
    percent: float | None = 61.0,
    age: timedelta = timedelta(seconds=1),
    detail: str | None = None,
) -> ActivityEvent:
    payload = {
        "status": status,
        "percent": percent,
        "eta_seconds": 240.0,
        "relative_media_path": path,
        "message": "Refiner is writing the cleaned-up file.",
    }
    row = ActivityEvent(
        event_type=activity_constants.REFINER_FILE_PROCESSING_PROGRESS,
        module="refiner",
        title="Refiner is processing",
        detail=detail if detail is not None else json.dumps(payload),
        created_at=utcnow() - age,
    )
    session.add(row)
    session.flush()
    return row


def test_nothing_in_flight_is_the_normal_case(db_session: Session) -> None:
    assert live_progress_by_path(db_session) == {}


def test_a_running_pass_is_reported(db_session: Session) -> None:
    _progress_row(db_session)
    live = live_progress_by_path(db_session)

    assert _PATH in live
    assert live[_PATH].percent == 61.0
    assert live[_PATH].eta_seconds == 240.0
    assert live[_PATH].message


def test_a_finished_pass_is_not_drawn_as_in_flight(db_session: Session) -> None:
    """The pass's last word is not progress — a finished file must not show a bar."""

    _progress_row(db_session, status="finished", percent=100.0)
    assert live_progress_by_path(db_session) == {}


def test_a_failed_pass_is_not_drawn_as_in_flight(db_session: Session) -> None:
    _progress_row(db_session, status="failed")
    assert live_progress_by_path(db_session) == {}


def test_stale_progress_is_ignored(db_session: Session) -> None:
    """A pass that stopped without a final update must not show 61% forever."""

    _progress_row(db_session, age=STALE_AFTER + timedelta(minutes=1))
    assert live_progress_by_path(db_session) == {}


def test_the_newest_row_wins_for_a_path(db_session: Session) -> None:
    _progress_row(db_session, percent=10.0, age=timedelta(minutes=1))
    _progress_row(db_session, percent=75.0, age=timedelta(seconds=1))

    assert live_progress_by_path(db_session)[_PATH].percent == 75.0


def test_a_malformed_payload_never_breaks_the_page(db_session: Session) -> None:
    """The payload is written by another process; one odd row must not fail a page load."""

    _progress_row(db_session, detail="not json at all")
    _progress_row(db_session, path="movies/Other.mkv", percent=42.0)

    live = live_progress_by_path(db_session)
    assert "movies/Other.mkv" in live
    assert _PATH not in live


def test_percent_is_clamped(db_session: Session) -> None:
    _progress_row(db_session, percent=150.0)
    assert live_progress_by_path(db_session)[_PATH].percent == 100.0
