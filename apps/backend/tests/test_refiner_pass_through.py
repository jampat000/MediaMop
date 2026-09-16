"""Never strand a file (#465).

These tests exist because this code copies people's media into the folder their media manager
imports from. The properties that matter most are pinned directly: the delivered copy is identical,
the source is never deleted, an existing output is respected, and nothing half-written is published.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from mediamop.core.config import MediaMopSettings
from mediamop.core.db import create_db_engine, create_session_factory
from mediamop.modules.refiner import refiner_pass_through
from mediamop.modules.refiner.jobs_model import RefinerJob
from mediamop.modules.refiner.refiner_file_state_model import RefinerFileRow, RefinerFileStatus
from mediamop.modules.refiner.refiner_library_model import RefinerLibraryRow
from mediamop.modules.refiner.refiner_pass_through import (
    REFINER_FILE_PASS_THROUGH_JOB_KIND,
    DeliverySettings,
    PassThroughIntegrityError,
    _make_byte_integrity_check,
    apply_failure_policy,
    deliver_unchanged,
    make_refiner_file_pass_through_handler,
    normalize_failure_policy,
)
from mediamop.platform.activity import constants as activity_constants
from mediamop.platform.activity.models import ActivityEvent
from tests.refiner_library_fixtures import seed_refiner_library

_REL = "Arrival (2016)/Arrival.2016.2160p.mkv"
_BYTES = b"\x1a\x45\xdf\xa3" + bytes(range(256)) * 40


@pytest.fixture
def folders(tmp_path: Path) -> tuple[Path, Path]:
    watched = tmp_path / "completed"
    output = tmp_path / "refined"
    (watched / Path(_REL).parent).mkdir(parents=True)
    output.mkdir()
    (watched / _REL).write_bytes(_BYTES)
    return watched, output


def _settings(watched: Path, output: Path, policy: str | None = "replace") -> DeliverySettings:
    return DeliverySettings(
        library_id=1,
        watched_folder=str(watched),
        output_folder=str(output),
        output_collision_policy=policy,
    )


# --- delivery: the filesystem guarantees -------------------------------------------------------


def test_the_original_is_delivered_byte_for_byte(folders: tuple[Path, Path]) -> None:
    watched, output = folders
    result = deliver_unchanged(_settings(watched, output), relative_path=_REL)

    assert result.delivered is True
    assert (output / _REL).read_bytes() == _BYTES


def test_the_source_is_never_deleted(folders: tuple[Path, Path]) -> None:
    """Deleting the only known-good copy straight after a failure is irreversible."""

    watched, output = folders
    deliver_unchanged(_settings(watched, output), relative_path=_REL)

    assert (watched / _REL).is_file()
    assert (watched / _REL).read_bytes() == _BYTES


def test_nothing_half_written_is_left_in_the_output_folder(folders: tuple[Path, Path]) -> None:
    """A manager watching the output folder must never see a partial file."""

    watched, output = folders
    deliver_unchanged(_settings(watched, output), relative_path=_REL)

    leftovers = [p.name for p in (output / Path(_REL).parent).iterdir() if p.name.endswith(".partial")]
    assert leftovers == []


def test_an_existing_output_is_respected_under_skip(folders: tuple[Path, Path]) -> None:
    watched, output = folders
    existing = output / _REL
    existing.parent.mkdir(parents=True)
    existing.write_bytes(b"the operator's existing output")

    result = deliver_unchanged(_settings(watched, output, policy="skip"), relative_path=_REL)

    assert result.delivered is False
    assert existing.read_bytes() == b"the operator's existing output"
    assert "kept the one that was already there" in result.sentence


def test_output_and_watched_being_the_same_folder_is_refused(folders: tuple[Path, Path]) -> None:
    watched, _ = folders
    with pytest.raises(RuntimeError, match="would overwrite the original"):
        deliver_unchanged(_settings(watched, watched), relative_path=_REL)
    assert (watched / _REL).read_bytes() == _BYTES


def test_a_vanished_source_is_reported_not_invented(folders: tuple[Path, Path]) -> None:
    watched, output = folders
    (watched / _REL).unlink()
    with pytest.raises(FileNotFoundError):
        deliver_unchanged(_settings(watched, output), relative_path=_REL)
    assert not (output / _REL).exists()


# --- integrity: byte-identical, not valid-media ------------------------------------------------


def test_integrity_passes_an_identical_copy(tmp_path: Path) -> None:
    source = tmp_path / "source.mkv"
    staged = tmp_path / "staged.mkv"
    source.write_bytes(_BYTES)
    staged.write_bytes(_BYTES)
    _make_byte_integrity_check(source)(staged)


def test_integrity_rejects_a_truncated_copy(tmp_path: Path) -> None:
    source = tmp_path / "source.mkv"
    staged = tmp_path / "staged.mkv"
    source.write_bytes(_BYTES)
    staged.write_bytes(_BYTES[:-10])
    with pytest.raises(PassThroughIntegrityError, match="bytes"):
        _make_byte_integrity_check(source)(staged)


def test_integrity_rejects_a_source_that_changed_during_the_copy(tmp_path: Path) -> None:
    source = tmp_path / "source.mkv"
    staged = tmp_path / "staged.mkv"
    source.write_bytes(_BYTES)
    check = _make_byte_integrity_check(source)
    source.write_bytes(_BYTES + b"still downloading")
    staged.write_bytes(_BYTES)
    with pytest.raises(PassThroughIntegrityError, match="changed"):
        check(staged)


def test_integrity_does_not_require_the_file_to_be_valid_media(tmp_path: Path) -> None:
    """A file that failed processing may not probe. "Unchanged" is the promise, not "valid"."""

    source = tmp_path / "corrupt.mkv"
    staged = tmp_path / "staged.mkv"
    garbage = b"this is not a matroska file at all"
    source.write_bytes(garbage)
    staged.write_bytes(garbage)
    _make_byte_integrity_check(source)(staged)


# --- policy -------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("pass_through", "pass_through"),
        ("hold", "hold"),
        ("HOLD", "hold"),
        ("", "pass_through"),
        (None, "pass_through"),
        ("nonsense", "pass_through"),
    ],
)
def test_an_unreadable_policy_falls_back_to_the_guarantee(raw: str | None, expected: str) -> None:
    """An unreadable setting must not quietly start stranding files again."""

    assert normalize_failure_policy(raw) == expected


@pytest.fixture
def db_session() -> Iterator[Session]:
    settings = MediaMopSettings.load()
    factory = create_session_factory(create_db_engine(settings))
    with factory() as session:
        session.execute(delete(RefinerJob))
        session.execute(delete(RefinerFileRow))
        session.commit()
        yield session
        session.rollback()
        session.execute(delete(RefinerJob))
        session.execute(delete(RefinerFileRow))
        session.commit()


def _pass_through_jobs(session: Session) -> list[RefinerJob]:
    return list(session.scalars(select(RefinerJob).where(RefinerJob.job_kind == REFINER_FILE_PASS_THROUGH_JOB_KIND)))


def test_nothing_happens_while_a_retry_is_still_coming(db_session: Session) -> None:
    library = seed_refiner_library(db_session, failure_policy="pass_through")
    assert apply_failure_policy(db_session, library=library, relative_path=_REL, will_retry=True) is None
    assert _pass_through_jobs(db_session) == []


def test_hold_keeps_the_file_as_before(db_session: Session) -> None:
    library = seed_refiner_library(db_session, failure_policy="hold")
    assert apply_failure_policy(db_session, library=library, relative_path=_REL, will_retry=False) is None
    assert _pass_through_jobs(db_session) == []


def test_pass_through_queues_a_delivery_once_retries_run_out(db_session: Session) -> None:
    library = seed_refiner_library(db_session, failure_policy="pass_through")
    assert apply_failure_policy(db_session, library=library, relative_path=_REL, will_retry=False) == "pass_through"
    assert len(_pass_through_jobs(db_session)) == 1


def test_repeated_failures_do_not_queue_racing_deliveries(db_session: Session) -> None:
    library = seed_refiner_library(db_session, failure_policy="pass_through")
    apply_failure_policy(db_session, library=library, relative_path=_REL, will_retry=False)
    apply_failure_policy(db_session, library=library, relative_path=_REL, will_retry=False)
    assert len(_pass_through_jobs(db_session)) == 1


def test_the_managers_hand_off_rides_along_with_the_delivery(db_session: Session) -> None:
    """The delivery is what a waiting manager finally hears about, so it has to know who asked."""

    library = seed_refiner_library(db_session, failure_policy="pass_through")
    origin = {"source_key": "deluno", "handoff_id": "h1", "library_id": "lib-movies", "callback_path": "/cb"}
    apply_failure_policy(db_session, library=library, relative_path=_REL, will_retry=False, origin=origin)
    (job,) = _pass_through_jobs(db_session)
    assert json.loads(job.payload_json or "{}")["origin"] == origin


def test_new_libraries_default_to_the_guarantee(db_session: Session) -> None:
    library = RefinerLibraryRow(name="Fresh", media_scope="movie")
    db_session.add(library)
    db_session.flush()
    db_session.refresh(library)
    assert library.failure_policy == "pass_through"


# --- the handler, end to end -------------------------------------------------------------------


@dataclass
class _Ctx:
    id: int
    payload_json: str


def test_the_handler_delivers_marks_and_records(
    db_session: Session,
    folders: tuple[Path, Path],
) -> None:
    watched, output = folders
    library = seed_refiner_library(
        db_session,
        watched_folder=str(watched),
        output_folder=str(output),
        failure_policy="pass_through",
    )
    db_session.add(
        RefinerFileRow(
            library_id=library.id,
            relative_path=_REL,
            status=RefinerFileStatus.PROCESSING_FAILED.value,
            status_reason="ffmpeg could not read the audio track.",
        ),
    )
    db_session.commit()

    settings = MediaMopSettings.load()
    handler = make_refiner_file_pass_through_handler(settings, create_session_factory(create_db_engine(settings)))
    handler(_Ctx(id=7, payload_json=json.dumps({"relative_media_path": _REL, "library_id": library.id})))

    db_session.expire_all()
    row = db_session.scalars(select(RefinerFileRow).where(RefinerFileRow.relative_path == _REL)).one()
    assert row.status == RefinerFileStatus.PASSED_THROUGH.value
    assert "handed the original back unchanged" in row.status_reason

    assert (output / _REL).read_bytes() == _BYTES
    assert (watched / _REL).is_file()

    events = list(
        db_session.scalars(
            select(ActivityEvent).where(ActivityEvent.event_type == activity_constants.REFINER_FILE_PASSED_THROUGH),
        ),
    )
    assert events
    assert json.loads(events[-1].detail or "{}")["source_kept"] is True


def test_a_delivered_hand_off_is_reported_to_the_waiting_manager(
    db_session: Session,
    folders: tuple[Path, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    watched, output = folders
    library = seed_refiner_library(
        db_session,
        watched_folder=str(watched),
        output_folder=str(output),
        failure_policy="pass_through",
    )
    db_session.commit()
    reports: list[dict[str, Any]] = []

    def _capture(session: Session, settings: MediaMopSettings, *, payload_json: str, result: dict[str, Any]) -> str:
        reports.append({"payload": json.loads(payload_json), "result": result})
        return "reported completed to Deluno"

    monkeypatch.setattr(refiner_pass_through, "report_handoff_completion", _capture)
    origin = {"source_key": "deluno", "handoff_id": "h1", "library_id": "lib-movies", "callback_path": "/cb"}

    settings = MediaMopSettings.load()
    handler = make_refiner_file_pass_through_handler(settings, create_session_factory(create_db_engine(settings)))
    handler(
        _Ctx(id=9, payload_json=json.dumps({"relative_media_path": _REL, "library_id": library.id, "origin": origin}))
    )

    (report,) = reports
    assert report["payload"]["origin"] == origin
    assert report["result"]["ok"] is True
    assert report["result"]["passed_through_after_failure"] is True
    assert Path(report["result"]["output_file"]) == (output / _REL).resolve()
    assert Path(report["result"]["refiner_output_folder_resolved"]) == output.resolve()


def test_a_delivery_that_did_not_come_from_a_manager_reports_nothing(
    db_session: Session,
    folders: tuple[Path, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    watched, output = folders
    library = seed_refiner_library(
        db_session,
        watched_folder=str(watched),
        output_folder=str(output),
        failure_policy="pass_through",
    )
    db_session.commit()
    reports: list[Any] = []
    monkeypatch.setattr(refiner_pass_through, "report_handoff_completion", lambda *a, **k: reports.append(k) or "")

    settings = MediaMopSettings.load()
    handler = make_refiner_file_pass_through_handler(settings, create_session_factory(create_db_engine(settings)))
    handler(_Ctx(id=10, payload_json=json.dumps({"relative_media_path": _REL, "library_id": library.id})))

    assert (output / _REL).read_bytes() == _BYTES
    assert reports == []


def test_a_failed_delivery_is_recorded_and_the_original_survives(
    db_session: Session,
    folders: tuple[Path, Path],
) -> None:
    watched, _ = folders
    library = seed_refiner_library(
        db_session,
        watched_folder=str(watched),
        output_folder=str(watched),  # misconfigured: output is the watched folder
        failure_policy="pass_through",
    )
    db_session.commit()

    settings = MediaMopSettings.load()
    handler = make_refiner_file_pass_through_handler(settings, create_session_factory(create_db_engine(settings)))
    with pytest.raises(RuntimeError):
        handler(_Ctx(id=8, payload_json=json.dumps({"relative_media_path": _REL, "library_id": library.id})))

    assert (watched / _REL).read_bytes() == _BYTES
    db_session.expire_all()
    failures = list(
        db_session.scalars(
            select(ActivityEvent).where(
                ActivityEvent.event_type == activity_constants.REFINER_FILE_PASS_THROUGH_FAILED,
            ),
        ),
    )
    assert failures
    assert "untouched" in (json.loads(failures[-1].detail or "{}").get("next_action") or "")


def test_a_pass_through_is_never_counted_as_a_completed_pass() -> None:
    """Savings are counted from completed passes; a hand-back must use a different event type."""

    assert activity_constants.REFINER_FILE_PASSED_THROUGH != activity_constants.REFINER_FILE_REMUX_PASS_COMPLETED
    assert RefinerFileStatus.PASSED_THROUGH.value != RefinerFileStatus.PROCESSED.value
