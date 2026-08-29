"""The durable per-file processing record, and its own retention.

Refiner computed every decision it made about a file and put it in an activity payload
that then aged out under the suite's log retention. "Why did this file come out like
that, three weeks ago" had no answer (#340).

The case worth being careful about is retention ``0``. The setting says it keeps records
forever; reading it as "delete everything" would silently destroy the history the feature
exists to keep, which is the worst possible direction for that ambiguity — so it has its
own test rather than being covered incidentally.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

import mediamop.modules.refiner.refiner_file_log_model  # noqa: F401
import mediamop.modules.refiner.refiner_file_state_model  # noqa: F401
import mediamop.modules.refiner.refiner_library_model  # noqa: F401
import mediamop.modules.refiner.refiner_operator_settings_model  # noqa: F401
from mediamop.core.db import Base
from mediamop.modules.refiner.refiner_file_log_model import RefinerFileLogRow
from mediamop.modules.refiner.refiner_file_log_service import (
    MAX_DETAIL_CHARS,
    logs_for_file,
    prune_file_logs,
    record_file_log,
    render_log_text,
)
from mediamop.modules.refiner.refiner_file_state_model import RefinerFileRow
from mediamop.modules.refiner.refiner_library_model import RefinerLibraryRow

NOW = datetime(2026, 8, 26, 14, 0, tzinfo=UTC)


@pytest.fixture
def session(tmp_path: Path) -> Session:
    engine = create_engine(
        f"sqlite:///{tmp_path / 'log.sqlite'}",
        connect_args={"check_same_thread": False},
        future=True,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, class_=Session, autoflush=False, autocommit=False, future=True)()


def _library(session: Session, name: str = "Movies") -> RefinerLibraryRow:
    row = RefinerLibraryRow(
        name=name,
        media_scope="movie",
        enabled=True,
        watched_folder="/srv/in",
        output_folder="/srv/out",
    )
    session.add(row)
    session.commit()
    return row


def _file(session: Session, library: RefinerLibraryRow, path: str = "Film/film.mkv") -> RefinerFileRow:
    row = RefinerFileRow(library_id=library.id, relative_path=path)
    session.add(row)
    session.commit()
    return row


# --- writing ------------------------------------------------------------------------


def test_a_record_keeps_the_whole_pass_payload(session: Session) -> None:
    library = _library(session)
    _file(session, library)

    record_file_log(
        session,
        relative_path="Film/film.mkv",
        title="Remuxed Film",
        detail={
            "outcome": "live_output_written",
            "ffmpeg_argv": ["ffmpeg", "-i", "in.mkv"],
            "audio_before": "eng, fra",
            "size_before_bytes": 1000,
            "size_after_bytes": 900,
        },
        recorded_at=NOW,
    )
    session.commit()

    row = session.scalars(select(RefinerFileLogRow)).one()
    assert row.outcome == "live_output_written"
    assert row.library_name == "Movies"
    detail = json.loads(row.detail_json)
    # Whole, not summarised: the point is answering questions nobody has asked yet.
    assert detail["ffmpeg_argv"] == ["ffmpeg", "-i", "in.mkv"]
    assert detail["size_after_bytes"] == 900


def test_each_pass_is_its_own_record_so_the_history_survives(session: Session) -> None:
    """A file that failed twice and then succeeded has three things worth reading."""

    library = _library(session)
    _file(session, library)
    for outcome in ("failed_during_execution", "failed_during_execution", "live_output_written"):
        record_file_log(
            session,
            relative_path="Film/film.mkv",
            title="Pass",
            detail={"outcome": outcome},
            recorded_at=NOW,
        )
    session.commit()

    assert len(session.scalars(select(RefinerFileLogRow)).all()) == 3


def test_a_record_is_written_even_when_no_file_row_exists(session: Session) -> None:
    """The pass produced something worth keeping; a missing index row is not a reason to lose it."""

    record_file_log(session, relative_path="Orphan/orphan.mkv", title="Pass", detail={"outcome": "ok"}, recorded_at=NOW)
    session.commit()

    row = session.scalars(select(RefinerFileLogRow)).one()
    assert row.file_id is None
    assert row.relative_path == "Orphan/orphan.mkv"


def test_an_enormous_payload_is_shortened_and_says_so(session: Session) -> None:
    library = _library(session)
    _file(session, library)

    record_file_log(
        session,
        relative_path="Film/film.mkv",
        title="Pass",
        detail={"outcome": "ok", "noise": "x" * (MAX_DETAIL_CHARS + 10)},
        recorded_at=NOW,
    )
    session.commit()

    detail = json.loads(session.scalars(select(RefinerFileLogRow)).one().detail_json)
    assert detail["truncated"] is True
    # Said in the record rather than leaving a reader to wonder why the JSON stops.
    assert "shortened when it was saved" in detail["truncated_note"]
    assert detail["outcome"] == "ok"


def test_a_string_payload_is_accepted_as_well_as_a_mapping(session: Session) -> None:
    record_file_log(
        session,
        relative_path="Film/film.mkv",
        title="Pass",
        detail=json.dumps({"outcome": "ok"}),
        recorded_at=NOW,
    )
    session.commit()

    assert session.scalars(select(RefinerFileLogRow)).one().outcome == "ok"


def test_unparseable_stored_detail_is_kept_rather_than_dropped(session: Session) -> None:
    record_file_log(session, relative_path="a.mkv", title="Pass", detail="not json at all", recorded_at=NOW)
    session.commit()

    detail = json.loads(session.scalars(select(RefinerFileLogRow)).one().detail_json)
    assert "unparsed_detail" in detail


# --- reading ------------------------------------------------------------------------


def test_records_are_returned_newest_first(session: Session) -> None:
    library = _library(session)
    file_row = _file(session, library)
    record_file_log(session, relative_path="Film/film.mkv", title="Old", detail={"outcome": "a"}, recorded_at=NOW)
    record_file_log(
        session,
        relative_path="Film/film.mkv",
        title="New",
        detail={"outcome": "b"},
        recorded_at=NOW + timedelta(hours=1),
    )
    session.commit()

    rows = logs_for_file(session, file_id=file_row.id)

    assert [r.title for r in rows] == ["New", "Old"]


def test_records_survive_the_file_being_forgotten_and_seen_again(session: Session) -> None:
    """Forgetting a file from the screen must not destroy the record of what was done to it."""

    library = _library(session)
    first = _file(session, library)
    record_file_log(session, relative_path="Film/film.mkv", title="Pass", detail={"outcome": "ok"}, recorded_at=NOW)
    session.commit()

    session.delete(first)
    session.commit()
    assert session.scalars(select(RefinerFileLogRow)).one() is not None

    # Seen again by a later scan: the history reattaches by path.
    again = _file(session, library)
    assert len(logs_for_file(session, file_id=again.id)) == 1


def test_a_file_that_does_not_exist_has_no_records(session: Session) -> None:
    assert logs_for_file(session, file_id=9999) == []


def test_the_text_rendering_is_readable_rather_than_minified_json(session: Session) -> None:
    library = _library(session)
    file_row = _file(session, library)
    record_file_log(
        session,
        relative_path="Film/film.mkv",
        title="Remuxed Film",
        detail={"outcome": "live_output_written", "ffmpeg_argv": ["ffmpeg", "-i", "in.mkv"]},
        recorded_at=NOW,
    )
    session.commit()

    text = render_log_text(logs_for_file(session, file_id=file_row.id))

    assert "Film/film.mkv" in text
    assert "Library: Movies" in text
    assert "live_output_written" in text
    assert "ffmpeg" in text


def test_the_text_rendering_says_so_when_there_is_nothing(session: Session) -> None:
    assert "no retained processing records" in render_log_text([])


# --- retention ----------------------------------------------------------------------


def test_records_past_the_retention_window_are_removed(session: Session) -> None:
    record_file_log(
        session, relative_path="a.mkv", title="Old", detail={"outcome": "a"}, recorded_at=NOW - timedelta(days=100)
    )
    record_file_log(
        session, relative_path="b.mkv", title="Recent", detail={"outcome": "b"}, recorded_at=NOW - timedelta(days=10)
    )
    session.commit()

    removed = prune_file_logs(session, retention_days=90, now=NOW)
    session.commit()

    assert removed == 1
    remaining = session.scalars(select(RefinerFileLogRow)).all()
    assert [r.title for r in remaining] == ["Recent"]


def test_zero_retention_keeps_everything_forever(session: Session) -> None:
    """The setting says 0 keeps records forever.

    Reading it as "delete everything" would silently destroy the history this feature
    exists to keep — the worst possible direction for that ambiguity, so it is asserted
    directly rather than covered incidentally.
    """

    record_file_log(
        session,
        relative_path="ancient.mkv",
        title="Ancient",
        detail={"outcome": "a"},
        recorded_at=NOW - timedelta(days=3650),
    )
    session.commit()

    removed = prune_file_logs(session, retention_days=0, now=NOW)
    session.commit()

    assert removed == 0
    assert len(session.scalars(select(RefinerFileLogRow)).all()) == 1


def test_a_negative_retention_is_treated_as_forever_too(session: Session) -> None:
    record_file_log(
        session,
        relative_path="ancient.mkv",
        title="Ancient",
        detail={"outcome": "a"},
        recorded_at=NOW - timedelta(days=3650),
    )
    session.commit()

    assert prune_file_logs(session, retention_days=-1, now=NOW) == 0


def test_pruning_an_empty_table_is_not_an_error(session: Session) -> None:
    assert prune_file_logs(session, retention_days=30, now=NOW) == 0


def test_a_record_exactly_on_the_boundary_is_kept(session: Session) -> None:
    # Strictly older than the cutoff, so "exactly 90 days" survives rather than being
    # removed by a rounding decision nobody made deliberately.
    record_file_log(
        session,
        relative_path="edge.mkv",
        title="Edge",
        detail={"outcome": "a"},
        recorded_at=NOW - timedelta(days=90),
    )
    session.commit()

    assert prune_file_logs(session, retention_days=90, now=NOW) == 0
