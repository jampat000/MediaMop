"""Retry, requeue, and the difference between a failure worth trying again and one that is not.

Refiner deletes source release folders after success. A file that failed recorded an
activity row and stopped: no retry, no requeue, no way back. The destructive path was
carefully engineered and the recovery path barely existed (#339).

The load-bearing distinction here is between a **preflight** failure and an **execution**
one. A file with no retainable audio will still have none in five minutes; an ffmpeg
process that died is the same file meeting a different world. Retrying the first burns a
worker slot to reach the same conclusion.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

import mediamop.modules.refiner.jobs_model  # noqa: F401
import mediamop.modules.refiner.refiner_file_state_model  # noqa: F401
import mediamop.modules.refiner.refiner_library_model  # noqa: F401
from mediamop.core.db import Base
from mediamop.modules.refiner.jobs_model import RefinerJob
from mediamop.modules.refiner.refiner_failure_classes import (
    RefinerFailureClass,
    backoff_seconds_for_attempt,
    classify_failure,
    is_retryable,
)
from mediamop.modules.refiner.refiner_file_state_model import RefinerFileRow, RefinerFileStatus
from mediamop.modules.refiner.refiner_library_model import RefinerLibraryRow
from mediamop.modules.refiner.refiner_requeue_service import (
    decide_retry,
    files_due_for_automatic_retry,
    record_failure,
    requeue_file,
    requeue_files,
)

NOW = datetime(2026, 8, 26, 14, 0, tzinfo=UTC)


def _as_utc(value: datetime | None) -> datetime | None:
    """SQLite stores datetimes without a timezone; reattach UTC for comparison."""

    if value is None:
        return None
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


@pytest.fixture
def session(tmp_path: Path) -> Session:
    engine = create_engine(
        f"sqlite:///{tmp_path / 'retry.sqlite'}",
        connect_args={"check_same_thread": False},
        future=True,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, class_=Session, autoflush=False, autocommit=False, future=True)()


def _library(session: Session, **overrides) -> RefinerLibraryRow:
    row = RefinerLibraryRow(
        name=overrides.pop("name", "Movies"),
        media_scope="movie",
        enabled=True,
        watched_folder="/srv/in",
        output_folder="/srv/out",
        schedule_enabled=False,
        max_attempts=overrides.pop("max_attempts", 3),
        retry_backoff_seconds=overrides.pop("retry_backoff_seconds", 300),
        retry_execution_failures=overrides.pop("retry_execution_failures", True),
        retry_preflight_failures=overrides.pop("retry_preflight_failures", False),
        **overrides,
    )
    session.add(row)
    session.commit()
    return row


def _remux_jobs(session: Session) -> list[RefinerJob]:
    return [j for j in session.scalars(select(RefinerJob)).all() if j.job_kind == "refiner.file.remux_pass.v1"]


# --- classification -----------------------------------------------------------------


def test_the_two_failure_moments_map_to_different_classes() -> None:
    assert classify_failure("failed_before_execution") is RefinerFailureClass.PREFLIGHT
    assert classify_failure("failed_during_execution") is RefinerFailureClass.EXECUTION
    assert classify_failure("skipped_guardrail") is RefinerFailureClass.GUARDRAIL


def test_anything_unrecognised_is_unknown_rather_than_assumed_retryable() -> None:
    assert classify_failure(None) is RefinerFailureClass.UNKNOWN
    assert classify_failure("something-new") is RefinerFailureClass.UNKNOWN
    assert (
        is_retryable(RefinerFailureClass.UNKNOWN, retry_preflight_failures=True, retry_execution_failures=True) is False
    )


def test_a_guardrail_is_never_retried_however_the_policy_is_set() -> None:
    """The guardrail is the answer, not an obstacle to route around."""

    assert (
        is_retryable(RefinerFailureClass.GUARDRAIL, retry_preflight_failures=True, retry_execution_failures=True)
        is False
    )


def test_the_backoff_doubles_and_is_capped_at_an_hour() -> None:
    assert backoff_seconds_for_attempt(attempt=1, base_seconds=300) == 300
    assert backoff_seconds_for_attempt(attempt=2, base_seconds=300) == 600
    assert backoff_seconds_for_attempt(attempt=3, base_seconds=300) == 1200
    # Capped, so a long-lived queue does not quietly schedule a retry for next week.
    assert backoff_seconds_for_attempt(attempt=20, base_seconds=300) == 3600


# --- policy -------------------------------------------------------------------------


def test_an_execution_failure_is_retried_by_default(session: Session) -> None:
    library = _library(session)

    decision = decide_retry(library=library, failure_class=RefinerFailureClass.EXECUTION, attempts_so_far=1, now=NOW)

    assert decision.will_retry is True
    # After one failure the wait is the configured base, and doubles from there. Indexing
    # by the *next* attempt number would skip the base delay and make the first retry
    # twice as slow as the setting says.
    assert decision.next_retry_at == NOW + timedelta(seconds=300)
    assert "attempt 2 of 3" in decision.reason


def test_the_backoff_doubles_on_the_second_failure(session: Session) -> None:
    library = _library(session)

    decision = decide_retry(library=library, failure_class=RefinerFailureClass.EXECUTION, attempts_so_far=2, now=NOW)

    assert decision.next_retry_at == NOW + timedelta(seconds=600)


def test_a_preflight_failure_is_not_retried_by_default_and_says_why(session: Session) -> None:
    """It will reach the same conclusion, so the reason points at the fix instead."""

    library = _library(session)

    decision = decide_retry(library=library, failure_class=RefinerFailureClass.PREFLIGHT, attempts_so_far=1, now=NOW)

    assert decision.will_retry is False
    assert decision.next_retry_at is None
    assert "same conclusion" in decision.reason
    assert "by hand" in decision.reason


def test_a_library_can_opt_into_retrying_preflight_failures(session: Session) -> None:
    library = _library(session, retry_preflight_failures=True)

    decision = decide_retry(library=library, failure_class=RefinerFailureClass.PREFLIGHT, attempts_so_far=1, now=NOW)

    assert decision.will_retry is True


def test_a_library_can_opt_out_of_retrying_execution_failures(session: Session) -> None:
    library = _library(session, name="Flaky NAS", retry_execution_failures=False)

    decision = decide_retry(library=library, failure_class=RefinerFailureClass.EXECUTION, attempts_so_far=1, now=NOW)

    assert decision.will_retry is False
    assert "Flaky NAS" in decision.reason


def test_attempts_are_exhausted_and_the_reason_names_the_limit(session: Session) -> None:
    library = _library(session, max_attempts=2)

    decision = decide_retry(library=library, failure_class=RefinerFailureClass.EXECUTION, attempts_so_far=2, now=NOW)

    assert decision.will_retry is False
    assert "allows 2" in decision.reason
    # And it points at the way out, rather than reading as a dead end.
    assert "by hand" in decision.reason


# --- recording a failure ------------------------------------------------------------


def test_recording_a_failure_classifies_it_and_schedules_the_retry(session: Session) -> None:
    library = _library(session)

    decision = record_failure(
        session,
        library=library,
        relative_path="Film/film.mkv",
        failure_class=RefinerFailureClass.EXECUTION,
        reason="ffmpeg exited with code 1.",
        now=NOW,
    )
    session.commit()

    row = session.scalars(select(RefinerFileRow)).one()
    assert row.status == RefinerFileStatus.PROCESSING_FAILED.value
    assert row.failure_class == "execution"
    assert row.failure_attempts == 1
    # SQLite hands datetimes back without a timezone, so compare the instant rather than
    # the object.
    assert _as_utc(row.next_retry_at) == NOW + timedelta(seconds=300)
    # The screen says whether a retry is coming without anyone knowing the policy.
    assert "ffmpeg exited" in row.status_reason
    assert "try again" in row.status_reason
    assert decision.will_retry is True


def test_repeated_failures_count_up_until_the_policy_stops(session: Session) -> None:
    library = _library(session, max_attempts=2)

    record_failure(
        session,
        library=library,
        relative_path="Film/film.mkv",
        failure_class=RefinerFailureClass.EXECUTION,
        reason="First failure.",
        now=NOW,
    )
    second = record_failure(
        session,
        library=library,
        relative_path="Film/film.mkv",
        failure_class=RefinerFailureClass.EXECUTION,
        reason="Second failure.",
        now=NOW,
    )
    session.commit()

    row = session.scalars(select(RefinerFileRow)).one()
    assert row.failure_attempts == 2
    assert second.will_retry is False
    assert row.next_retry_at is None


def test_a_preflight_failure_records_no_retry_time(session: Session) -> None:
    library = _library(session)

    record_failure(
        session,
        library=library,
        relative_path="Film/film.mkv",
        failure_class=RefinerFailureClass.PREFLIGHT,
        reason="No retainable audio track.",
        now=NOW,
    )
    session.commit()

    row = session.scalars(select(RefinerFileRow)).one()
    assert row.next_retry_at is None
    assert row.failure_class == "preflight"


# --- requeue ------------------------------------------------------------------------


def test_a_manual_requeue_works_after_the_attempts_are_spent(session: Session) -> None:
    """The point of the manual route: whoever asked has usually just fixed the problem.

    Making them wait out a backoff, or refusing because the automatic attempts are gone,
    would answer a question they did not ask.
    """

    library = _library(session, max_attempts=1)
    record_failure(
        session,
        library=library,
        relative_path="Film/film.mkv",
        failure_class=RefinerFailureClass.EXECUTION,
        reason="ffmpeg died.",
        now=NOW,
    )
    session.commit()
    row = session.scalars(select(RefinerFileRow)).one()
    assert row.failure_attempts == 1

    result = requeue_file(session, row=row, manual=True, now=NOW)
    session.commit()

    assert result.requeued == 1
    assert row.status == RefinerFileStatus.UNPROCESSED.value
    # The count resets, which is the whole difference between manual and automatic.
    assert row.failure_attempts == 0
    assert row.failure_class is None

    jobs = _remux_jobs(session)
    assert len(jobs) == 1
    # No backoff on a manual requeue.
    assert jobs[0].not_before is None


def test_an_automatic_requeue_keeps_the_count_and_honours_the_backoff(session: Session) -> None:
    library = _library(session)
    record_failure(
        session,
        library=library,
        relative_path="Film/film.mkv",
        failure_class=RefinerFailureClass.EXECUTION,
        reason="ffmpeg died.",
        now=NOW,
    )
    session.commit()
    row = session.scalars(select(RefinerFileRow)).one()

    requeue_file(session, row=row, manual=False, now=NOW)
    session.commit()

    assert row.failure_attempts == 1
    assert _remux_jobs(session)[0].not_before is not None


def test_a_requeued_job_carries_its_library_so_the_caps_still_apply(session: Session) -> None:
    import json

    library = _library(session)
    record_failure(
        session,
        library=library,
        relative_path="Film/film.mkv",
        failure_class=RefinerFailureClass.EXECUTION,
        reason="ffmpeg died.",
        now=NOW,
    )
    session.commit()
    requeue_file(session, row=session.scalars(select(RefinerFileRow)).one(), manual=True, now=NOW)
    session.commit()

    payload = json.loads(_remux_jobs(session)[0].payload_json or "{}")
    assert payload["library_id"] == library.id
    assert payload["relative_media_path"] == "Film/film.mkv"


def test_a_bulk_requeue_reports_a_total_rather_than_stopping_at_the_first_problem(session: Session) -> None:
    library = _library(session)
    rows = []
    for name in ("a.mkv", "b.mkv", "c.mkv"):
        record_failure(
            session,
            library=library,
            relative_path=name,
            failure_class=RefinerFailureClass.EXECUTION,
            reason="ffmpeg died.",
            now=NOW,
        )
    session.commit()
    rows = list(session.scalars(select(RefinerFileRow)))

    result = requeue_files(session, rows=rows, now=NOW)
    session.commit()

    assert result.requeued == 3
    assert result.skipped == 0
    assert "Queued 3 file(s)" in result.detail
    assert len(_remux_jobs(session)) == 3


def test_a_file_whose_library_is_gone_is_skipped_and_counted(session: Session) -> None:
    """A bulk action that stops halfway leaves an operator guessing which half ran."""

    library = _library(session)
    record_failure(
        session,
        library=library,
        relative_path="orphan.mkv",
        failure_class=RefinerFailureClass.EXECUTION,
        reason="ffmpeg died.",
        now=NOW,
    )
    session.commit()
    row = session.scalars(select(RefinerFileRow)).one()
    row.library_id = 9999
    session.commit()

    result = requeue_files(session, rows=[row], now=NOW)

    assert result.requeued == 0
    assert result.skipped == 1
    assert "no longer exists" in result.detail


def test_an_empty_bulk_requeue_says_nothing_matched(session: Session) -> None:
    result = requeue_files(session, rows=[], now=NOW)

    assert result.requeued == 0
    assert "Nothing matched" in result.detail


# --- which files are due ------------------------------------------------------------


def test_only_files_whose_backoff_has_elapsed_are_due(session: Session) -> None:
    library = _library(session)
    record_failure(
        session,
        library=library,
        relative_path="soon.mkv",
        failure_class=RefinerFailureClass.EXECUTION,
        reason="ffmpeg died.",
        now=NOW,
    )
    session.commit()

    assert files_due_for_automatic_retry(session, now=NOW) == []

    due = files_due_for_automatic_retry(session, now=NOW + timedelta(seconds=301))
    assert len(due) == 1
    assert due[0].relative_path == "soon.mkv"


def test_a_file_with_no_scheduled_retry_is_never_due(session: Session) -> None:
    library = _library(session)
    record_failure(
        session,
        library=library,
        relative_path="terminal.mkv",
        failure_class=RefinerFailureClass.PREFLIGHT,
        reason="No retainable audio track.",
        now=NOW,
    )
    session.commit()

    assert files_due_for_automatic_retry(session, now=NOW + timedelta(days=30)) == []
