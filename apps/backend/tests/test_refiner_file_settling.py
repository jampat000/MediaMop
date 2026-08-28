"""Deciding a file has finished being written by watching it, not by predicting it.

The old gate was one mtime comparison, which cannot distinguish "nobody is writing this"
from "the writer paused". Every test here is written against that distinction: the stalled
download is the case an mtime threshold gets wrong, and it is the reason this module
exists (#335).
"""

from __future__ import annotations

import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

import mediamop.modules.refiner.refiner_file_state_model  # noqa: F401
import mediamop.modules.refiner.refiner_library_model  # noqa: F401
import mediamop.platform.media_managers.connection_model  # noqa: F401
from mediamop.core.db import Base
from mediamop.modules.refiner.refiner_file_settling import (
    check_file_access,
    observe_size_settling,
)
from mediamop.modules.refiner.refiner_file_state_model import RefinerFileRow, RefinerFileStatus
from mediamop.modules.refiner.refiner_file_state_service import (
    decide_file_state,
    existing_file_row,
    record_file_state,
)
from mediamop.modules.refiner.refiner_library_model import RefinerLibraryRow

NOW = datetime(2026, 8, 29, 12, 0, tzinfo=UTC)


@pytest.fixture
def session(tmp_path: Path) -> Session:
    engine = create_engine(
        f"sqlite:///{tmp_path / 'settling.sqlite'}",
        connect_args={"check_same_thread": False},
        future=True,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, class_=Session, autoflush=False, autocommit=False, future=True)()


def _library(**overrides) -> RefinerLibraryRow:
    return RefinerLibraryRow(
        name=overrides.pop("name", "Movies"),
        media_scope="movie",
        enabled=overrides.pop("enabled", True),
        watched_folder="/srv/in",
        output_folder="/srv/out",
        min_file_age_seconds=overrides.pop("min_file_age_seconds", 0),
        hold_minutes=overrides.pop("hold_minutes", 0),
        schedule_enabled=False,
        file_detection_interval_seconds=overrides.pop("file_detection_interval_seconds", 30),
        ignore_size_changes=overrides.pop("ignore_size_changes", False),
        skip_access_tests=overrides.pop("skip_access_tests", False),
        **overrides,
    )


def _seen(size: int, *, changed_at: datetime | None) -> RefinerFileRow:
    return RefinerFileRow(
        library_id=1,
        relative_path="Film/film.mkv",
        size_bytes=size,
        size_changed_at=changed_at,
    )


def test_a_file_seen_for_the_first_time_is_treated_as_still_settling() -> None:
    # One observation cannot show that anything has stopped.
    obs = observe_size_settling(library=_library(), previous=None, current_size_bytes=1_000, now=NOW)

    assert obs.is_settling is True
    assert obs.stable_at == NOW + timedelta(seconds=30)
    assert "only just found" in (obs.reason or "")


def test_a_growing_file_stays_settling_and_restarts_the_clock() -> None:
    previous = _seen(1_000, changed_at=NOW - timedelta(minutes=5))

    obs = observe_size_settling(library=_library(), previous=previous, current_size_bytes=2_000, now=NOW)

    assert obs.is_settling is True
    # The clock restarts from this observation, not from the stale one.
    assert obs.size_changed_at == NOW
    assert obs.stable_at == NOW + timedelta(seconds=30)
    assert "still growing" in (obs.reason or "")


def test_a_size_that_has_held_still_long_enough_is_settled() -> None:
    previous = _seen(2_000, changed_at=NOW - timedelta(seconds=31))

    obs = observe_size_settling(library=_library(), previous=previous, current_size_bytes=2_000, now=NOW)

    assert obs.is_settling is False
    assert obs.reason is None


def test_a_size_that_has_only_just_stopped_is_not_settled_yet() -> None:
    previous = _seen(2_000, changed_at=NOW - timedelta(seconds=5))

    obs = observe_size_settling(library=_library(), previous=previous, current_size_bytes=2_000, now=NOW)

    assert obs.is_settling is True
    assert obs.stable_at == NOW - timedelta(seconds=5) + timedelta(seconds=30)


def test_a_stalled_download_that_resumes_starts_settling_again() -> None:
    """The case an mtime threshold gets wrong.

    A download stalls for an hour, so every age-based gate has long since elapsed and the
    file reads as finished. Then it resumes. Size settling sees the change and holds the
    file; nothing about the pause makes it look ready.
    """

    library = _library()

    stalled = _seen(2_000, changed_at=NOW - timedelta(hours=1))
    settled = observe_size_settling(library=library, previous=stalled, current_size_bytes=2_000, now=NOW)
    assert settled.is_settling is False

    resumed = observe_size_settling(library=library, previous=stalled, current_size_bytes=2_500, now=NOW)
    assert resumed.is_settling is True
    assert resumed.size_changed_at == NOW

    # And the scan after that one is measured from the resumption, not the stall.
    still_writing = _seen(2_500, changed_at=NOW)
    next_scan = observe_size_settling(
        library=library,
        previous=still_writing,
        current_size_bytes=2_500,
        now=NOW + timedelta(seconds=10),
    )
    assert next_scan.is_settling is True


def test_a_same_size_file_with_no_recorded_change_moment_is_not_assumed_settled() -> None:
    # Rows written before this feature existed have no size_changed_at. Unknown must not
    # read as settled, for the same reason "no queue signal" must not read as "empty".
    previous = _seen(2_000, changed_at=None)

    obs = observe_size_settling(library=_library(), previous=previous, current_size_bytes=2_000, now=NOW)

    assert obs.is_settling is True
    assert obs.size_changed_at == NOW


def test_ignore_size_changes_opts_a_library_out() -> None:
    previous = _seen(1_000, changed_at=NOW)

    obs = observe_size_settling(
        library=_library(ignore_size_changes=True), previous=previous, current_size_bytes=9_999, now=NOW
    )

    assert obs.is_settling is False


def test_a_zero_detection_interval_opts_out_too() -> None:
    obs = observe_size_settling(
        library=_library(file_detection_interval_seconds=0), previous=None, current_size_bytes=1, now=NOW
    )

    assert obs.is_settling is False


def test_an_unreadable_file_is_a_wait_with_a_reason_not_a_silent_skip(tmp_path: Path) -> None:
    missing = tmp_path / "not-there.mkv"

    check = check_file_access(library=_library(), file_path=missing, output_folder=tmp_path)

    assert check.ok is False
    assert "could not open this file for reading" in (check.problem or "")


def test_an_unwritable_output_folder_is_reported_before_any_work_starts(tmp_path: Path) -> None:
    source = tmp_path / "film.mkv"
    source.write_bytes(b"data")
    # A path whose parent is a *file* cannot be created as a directory on any platform,
    # which makes this an unwritable output root without needing real permissions.
    unwritable = source / "output"

    check = check_file_access(library=_library(), file_path=source, output_folder=unwritable)

    assert check.ok is False
    assert "cannot write to the output folder" in (check.problem or "")


def test_a_readable_file_and_writable_output_pass_and_leave_no_probe_behind(tmp_path: Path) -> None:
    source = tmp_path / "film.mkv"
    source.write_bytes(b"data")
    out = tmp_path / "out"
    out.mkdir()

    check = check_file_access(library=_library(), file_path=source, output_folder=out)

    assert check.ok is True
    assert list(out.iterdir()) == []


def test_skip_access_tests_opts_a_library_out(tmp_path: Path) -> None:
    check = check_file_access(
        library=_library(skip_access_tests=True),
        file_path=tmp_path / "not-there.mkv",
        output_folder=tmp_path / "also-not-there",
    )

    assert check.ok is True


def test_a_settling_file_reports_on_hold_with_the_settling_reason_and_a_release_time() -> None:
    verdict = decide_file_state(
        library=_library(),
        in_schedule_window=True,
        file_age_seconds=99_999,
        size_is_settling=True,
        settling_reason="This file is still growing, so something is writing to it.",
        settling_stable_at=NOW + timedelta(seconds=30),
    )

    assert verdict.status is RefinerFileStatus.ON_HOLD
    assert verdict.eligible is False
    assert verdict.hold_until == NOW + timedelta(seconds=30)
    assert "still growing" in verdict.reason


def test_settling_is_reported_ahead_of_an_access_problem() -> None:
    """A file being written is normally locked too, and the lock is not the cause."""

    verdict = decide_file_state(
        library=_library(),
        in_schedule_window=True,
        file_age_seconds=99_999,
        size_is_settling=True,
        settling_reason="This file is still growing, so something is writing to it.",
        access_problem="MediaMop could not open this file for reading.",
    )

    assert "still growing" in verdict.reason


def test_an_access_problem_holds_the_file_without_inventing_a_release_time() -> None:
    verdict = decide_file_state(
        library=_library(),
        in_schedule_window=True,
        file_age_seconds=99_999,
        access_problem="MediaMop could not open this file for reading.",
    )

    assert verdict.status is RefinerFileStatus.ON_HOLD
    assert verdict.hold_until is None


def test_an_access_problem_never_outranks_the_library_being_switched_off() -> None:
    verdict = decide_file_state(
        library=_library(enabled=False),
        in_schedule_window=True,
        file_age_seconds=99_999,
        access_problem="MediaMop could not open this file for reading.",
    )

    assert verdict.status is RefinerFileStatus.DISABLED


def test_the_hold_timer_reports_a_release_time_the_files_screen_can_show() -> None:
    verdict = decide_file_state(
        library=_library(min_file_age_seconds=60, hold_minutes=5),
        in_schedule_window=True,
        file_age_seconds=10,
    )

    assert verdict.status is RefinerFileStatus.ON_HOLD
    assert verdict.hold_until is not None
    # 60s minimum age + 5 minutes hold, minus the 10 seconds already elapsed.
    remaining = (verdict.hold_until - datetime.now(UTC)).total_seconds()
    assert 340 <= remaining <= 360
    assert "350s" in verdict.reason


def test_the_settled_state_survives_a_round_trip_through_the_row(session: Session) -> None:
    library = _library()
    session.add(library)
    session.commit()

    first = observe_size_settling(library=library, previous=None, current_size_bytes=1_000, now=NOW)
    record_file_state(
        session,
        library=library,
        relative_path="Film/film.mkv",
        verdict=decide_file_state(
            library=library,
            in_schedule_window=True,
            file_age_seconds=99_999,
            size_is_settling=first.is_settling,
            settling_reason=first.reason,
            settling_stable_at=first.stable_at,
        ),
        size_bytes=1_000,
        size_changed_at=first.size_changed_at,
    )
    session.commit()

    stored = existing_file_row(session, library_id=library.id, relative_path="Film/film.mkv")
    assert stored is not None
    assert stored.status == RefinerFileStatus.ON_HOLD.value
    assert stored.size_bytes == 1_000
    assert stored.hold_until is not None

    # The next scan reads that row back and finds the file has held still long enough.
    later = observe_size_settling(
        library=library, previous=stored, current_size_bytes=1_000, now=NOW + timedelta(seconds=31)
    )
    assert later.is_settling is False


@pytest.mark.skipif(sys.platform != "win32", reason="exclusive-lock semantics differ off Windows")
def test_a_file_held_open_exclusively_is_reported_as_locked(tmp_path: Path) -> None:
    import msvcrt

    source = tmp_path / "film.mkv"
    source.write_bytes(b"data" * 64)
    handle = source.open("r+b")
    try:
        msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        try:
            check = check_file_access(library=_library(), file_path=source, output_folder=tmp_path)
        finally:
            msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
    finally:
        handle.close()

    assert check.ok is False
    assert "locked" in (check.problem or "")
