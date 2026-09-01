"""The reasons a file is deliberately not being processed.

Refiner could previously say a job was pending, leased, completed or failed. None of
those answer "why isn't this file processing?", which is the question this vocabulary
exists for — so every test here asserts the *reason*, not just the status.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

import mediamop.modules.refiner.jobs_model  # noqa: F401
import mediamop.modules.refiner.refiner_file_state_model  # noqa: F401
import mediamop.modules.refiner.refiner_library_model  # noqa: F401
import mediamop.platform.media_managers.connection_model  # noqa: F401
from mediamop.core.db import Base
from mediamop.modules.refiner.refiner_file_state_model import (
    REFINER_WITHHELD_STATUSES,
    RefinerFileStatus,
)
from mediamop.modules.refiner.refiner_file_state_service import (
    decide_file_state,
    forget_file,
    list_files,
    mark_file_status,
    record_file_state,
    status_counts,
)
from mediamop.modules.refiner.refiner_library_model import RefinerLibraryRow


@pytest.fixture
def session(tmp_path: Path) -> Session:
    engine = create_engine(
        f"sqlite:///{tmp_path / 'files.sqlite'}",
        connect_args={"check_same_thread": False},
        future=True,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, class_=Session, autoflush=False, autocommit=False, future=True)()


def _library(session: Session, **overrides) -> RefinerLibraryRow:
    row = RefinerLibraryRow(
        name=overrides.pop("name", "Movies"),
        media_scope=overrides.pop("media_scope", "movie"),
        watched_folder="/srv/in",
        output_folder="/srv/out",
        min_file_age_seconds=overrides.pop("min_file_age_seconds", 60),
        **overrides,
    )
    session.add(row)
    session.commit()
    return row


def test_a_disabled_library_reports_disabled_and_says_which_one(session: Session) -> None:
    library = _library(session, name="Kids", enabled=False)
    verdict = decide_file_state(library=library, in_schedule_window=True, file_age_seconds=99999)
    assert verdict.status is RefinerFileStatus.DISABLED
    assert "Kids" in verdict.reason
    assert "switched off" in verdict.reason
    assert verdict.eligible is False


def test_outside_the_schedule_window_says_it_will_come_back(session: Session) -> None:
    library = _library(session, schedule_enabled=True)
    verdict = decide_file_state(library=library, in_schedule_window=False, file_age_seconds=99999)
    assert verdict.status is RefinerFileStatus.OUT_OF_SCHEDULE
    assert "window opens" in verdict.reason


def test_a_file_still_settling_is_on_hold(session: Session) -> None:
    library = _library(session)
    verdict = decide_file_state(library=library, in_schedule_window=True, file_age_seconds=99999, size_is_settling=True)
    assert verdict.status is RefinerFileStatus.ON_HOLD
    assert "still being written" in verdict.reason


def test_a_too_new_file_is_on_hold_and_says_how_much_longer(session: Session) -> None:
    library = _library(session, min_file_age_seconds=300)
    verdict = decide_file_state(library=library, in_schedule_window=True, file_age_seconds=60)
    assert verdict.status is RefinerFileStatus.ON_HOLD
    assert "300s" in verdict.reason
    assert "240s to go" in verdict.reason


def test_the_hold_timer_adds_to_the_minimum_age(session: Session) -> None:
    library = _library(session, min_file_age_seconds=60, hold_minutes=5)
    verdict = decide_file_state(library=library, in_schedule_window=True, file_age_seconds=100)
    assert verdict.status is RefinerFileStatus.ON_HOLD
    # 60 + 5*60 = 360
    assert "360s" in verdict.reason


def test_blocked_upstream_names_the_connection_not_the_vendor(session: Session) -> None:
    library = _library(session)
    verdict = decide_file_state(
        library=library,
        in_schedule_window=True,
        file_age_seconds=99999,
        blocked_by_connection="Deluno (Main)",
    )
    assert verdict.status is RefinerFileStatus.BLOCKED_UPSTREAM
    assert verdict.blocked_by_connection == "Deluno (Main)"
    assert "Deluno (Main) is still importing this file" in verdict.reason


def test_a_file_clearing_every_gate_is_eligible(session: Session) -> None:
    library = _library(session)
    verdict = decide_file_state(library=library, in_schedule_window=True, file_age_seconds=99999)
    assert verdict.status is RefinerFileStatus.UNPROCESSED
    assert verdict.eligible is True


def test_the_first_reason_wins_so_the_operator_sees_what_to_fix(session: Session) -> None:
    """A disabled library is the answer even when the file is also too new and blocked."""

    library = _library(session, enabled=False, min_file_age_seconds=999)
    verdict = decide_file_state(
        library=library,
        in_schedule_window=False,
        file_age_seconds=1,
        blocked_by_connection="Deluno (Main)",
    )
    assert verdict.status is RefinerFileStatus.DISABLED


def test_every_withheld_status_is_a_deliberate_decision_not_to_act() -> None:
    assert {
        "disabled",
        "on_hold",
        "out_of_schedule",
        "blocked_upstream",
        "skipped",
    } == REFINER_WITHHELD_STATUSES


def test_recording_a_state_is_idempotent_across_scans(session: Session) -> None:
    library = _library(session)
    first = decide_file_state(library=library, in_schedule_window=True, file_age_seconds=1)
    record_file_state(session, library=library, relative_path="a.mkv", verdict=first, size_bytes=2048)
    session.commit()

    second = decide_file_state(library=library, in_schedule_window=True, file_age_seconds=99999)
    row = record_file_state(session, library=library, relative_path="a.mkv", verdict=second)
    session.commit()

    assert len(list_files(session)) == 1
    assert row.status == RefinerFileStatus.UNPROCESSED.value
    assert row.size_bytes == 2048


def test_moving_out_of_blocked_upstream_clears_the_connection(session: Session) -> None:
    library = _library(session)
    blocked = decide_file_state(
        library=library, in_schedule_window=True, file_age_seconds=99999, blocked_by_connection="Radarr (4K)"
    )
    record_file_state(session, library=library, relative_path="a.mkv", verdict=blocked)
    session.commit()

    row = mark_file_status(
        session,
        library_id=library.id,
        relative_path="a.mkv",
        status=RefinerFileStatus.PROCESSING,
        reason="Refiner is working on this file now.",
    )
    session.commit()

    assert row is not None
    assert row.blocked_by_connection is None
    assert row.last_attempt_at is not None


def test_marking_a_file_mediamop_has_never_seen_does_nothing(session: Session) -> None:
    library = _library(session)
    assert (
        mark_file_status(
            session,
            library_id=library.id,
            relative_path="never-seen.mkv",
            status=RefinerFileStatus.PROCESSED,
            reason="done",
        )
        is None
    )


def test_status_counts_cover_every_bucket_even_when_empty(session: Session) -> None:
    library = _library(session)
    record_file_state(
        session,
        library=library,
        relative_path="a.mkv",
        verdict=decide_file_state(library=library, in_schedule_window=True, file_age_seconds=99999),
    )
    session.commit()

    counts = status_counts(session)

    assert counts["unprocessed"] == 1
    # Every bucket is present so the screen can render a zero rather than a gap.
    assert set(counts) == {s.value for s in RefinerFileStatus}
    assert counts["blocked_upstream"] == 0


def test_filters_narrow_by_library_status_and_path(session: Session) -> None:
    movies = _library(session, name="Movies")
    kids = _library(session, name="Kids")
    ready = decide_file_state(library=movies, in_schedule_window=True, file_age_seconds=99999)
    held = decide_file_state(library=kids, in_schedule_window=True, file_age_seconds=1)
    record_file_state(session, library=movies, relative_path="Film/movie.mkv", verdict=ready)
    record_file_state(session, library=kids, relative_path="Cartoon/toon.mkv", verdict=held)
    session.commit()

    assert len(list_files(session, library_id=movies.id)) == 1
    assert len(list_files(session, status="on_hold")) == 1
    assert len(list_files(session, path_contains="toon")) == 1
    assert len(list_files(session, since=datetime.now(UTC) + timedelta(days=1))) == 0


def test_forgetting_a_file_removes_only_the_record(session: Session) -> None:
    library = _library(session)
    row = record_file_state(
        session,
        library=library,
        relative_path="a.mkv",
        verdict=decide_file_state(library=library, in_schedule_window=True, file_age_seconds=99999),
    )
    session.commit()

    forget_file(session, row)
    session.commit()

    assert list_files(session) == []
