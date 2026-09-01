"""Refiner file activity handler keeps one live row per processed file."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from sqlalchemy import create_engine, delete, select
from sqlalchemy.orm import Session, sessionmaker

from mediamop.core.config import MediaMopSettings
from mediamop.core.db import Base, create_db_engine, create_session_factory
from mediamop.modules.refiner.file_remux_pass import handlers as handler_mod
from mediamop.modules.refiner.file_remux_pass.visibility import REMUX_PASS_OUTCOME_LIVE_OUTPUT_WRITTEN
from mediamop.modules.refiner.refiner_file_state_model import RefinerFileRow, RefinerFileStatus
from mediamop.modules.refiner.refiner_library_model import RefinerLibraryRow
from mediamop.modules.refiner.worker_loop import RefinerJobWorkContext
from mediamop.platform.activity import constants as activity_constants
from mediamop.platform.activity.live_stream import activity_latest_notifier
from mediamop.platform.activity.models import ActivityEvent


def test_refiner_remux_handler_updates_progress_row_to_completed_activity(
    monkeypatch,
) -> None:
    settings = MediaMopSettings.load()
    eng = create_db_engine(settings)
    fac = create_session_factory(eng)
    activity_latest_notifier.reset_for_tests()
    with fac() as db:
        assert isinstance(db, Session)
        db.execute(delete(ActivityEvent))
        db.commit()
    monkeypatch.setattr(
        handler_mod,
        "ensure_refiner_operator_settings_row",
        lambda _session: SimpleNamespace(
            min_file_age_seconds=0,
            refiner_min_input_file_size_mb=0,
            minimum_free_disk_space_mb=0,
        ),
    )
    monkeypatch.setattr(handler_mod, "load_refiner_remux_rules_config", lambda _session, *, media_scope: object())
    monkeypatch.setattr(
        handler_mod, "resolve_refiner_path_runtime_for_remux", lambda *_args, **_kwargs: (object(), None)
    )

    def _fake_run_refiner_file_remux_pass(**kwargs: Any) -> dict[str, Any]:
        progress_reporter = kwargs["progress_reporter"]
        progress_reporter(
            {
                "status": "processing",
                "relative_media_path": "Movie/file.mkv",
                "percent": 10.0,
                "message": "Refiner is writing the cleaned-up file.",
            }
        )
        progress_reporter(
            {
                "status": "processing",
                "relative_media_path": "Movie/file.mkv",
                "percent": 55.0,
                "message": "Refiner is writing the cleaned-up file.",
            }
        )
        return {
            "ok": True,
            "outcome": REMUX_PASS_OUTCOME_LIVE_OUTPUT_WRITTEN,
            "relative_media_path": "Movie/file.mkv",
            "source_size_bytes": 2000,
            "output_size_bytes": 1000,
        }

    monkeypatch.setattr(handler_mod, "run_refiner_file_remux_pass", _fake_run_refiner_file_remux_pass)

    handler = handler_mod.make_refiner_file_remux_pass_handler(settings, fac)
    handler(
        RefinerJobWorkContext(
            id=123,
            job_kind="refiner.file.remux_pass.v1",
            payload_json=json.dumps({"relative_media_path": "Movie/file.mkv", "media_scope": "movie"}),
            lease_owner="test",
        )
    )

    with fac() as db:
        rows = list(db.scalars(select(ActivityEvent).order_by(ActivityEvent.id)).all())

    assert len(rows) == 1
    row = rows[0]
    assert row.event_type == activity_constants.REFINER_FILE_REMUX_PASS_COMPLETED
    assert row.module == "refiner"
    assert row.title == "file.mkv was processed successfully"
    assert row.detail is not None
    detail = json.loads(row.detail)
    assert detail["outcome"] == REMUX_PASS_OUTCOME_LIVE_OUTPUT_WRITTEN
    assert detail["job_id"] == 123
    assert detail["source_size_bytes"] == 2000
    assert detail["output_size_bytes"] == 1000

    latest_id, revision = activity_latest_notifier.snapshot()
    assert latest_id == row.id
    assert revision == 3

    with fac() as db:
        assert isinstance(db, Session)
        db.execute(delete(ActivityEvent))
        db.commit()


def test_retryable_source_wait_returns_file_to_on_hold_without_counting_a_failure(tmp_path: Path) -> None:
    engine = create_engine(
        f"sqlite:///{tmp_path / 'wait.sqlite'}",
        connect_args={"check_same_thread": False},
        future=True,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, class_=Session, autoflush=False, autocommit=False, future=True)
    with factory() as session, session.begin():
        library = RefinerLibraryRow(
            name="Movies",
            media_scope="movie",
            watched_folder="C:/watched",
            output_folder="C:/output",
        )
        session.add(library)
        session.flush()
        library_id = library.id
        session.add(
            RefinerFileRow(
                library_id=library_id,
                relative_path="Testament/file.mkv",
                status=RefinerFileStatus.PROCESSING.value,
                status_reason="Processing",
                failure_class="execution",
                failure_attempts=2,
            )
        )

    result: dict[str, Any] = {
        "ok": False,
        "outcome": "source_not_ready",
        "retryable_wait": True,
        "relative_media_path": "Testament/file.mkv",
        "reason": "This file is still open for writing by another program.",
    }
    handler_mod._apply_file_outcome_state(
        factory,
        result=result,
        library_id=library_id,
        media_scope="movie",
    )

    with factory() as session:
        row = session.scalars(select(RefinerFileRow)).one()
        assert row.status == RefinerFileStatus.ON_HOLD.value
        assert row.failure_attempts == 0
        assert row.failure_class is None
        assert row.next_retry_at is None
        assert row.hold_until is None
    assert result["quarantined"] is False
    assert result["retry_scheduled"] is False


def test_rejected_no_video_file_uses_library_cleanup_policy_after_recording(tmp_path: Path) -> None:
    engine = create_engine(
        f"sqlite:///{tmp_path / 'rejected.sqlite'}",
        connect_args={"check_same_thread": False},
        future=True,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, class_=Session, autoflush=False, autocommit=False, future=True)
    watched = tmp_path / "watched"
    watched.mkdir()
    source = watched / "audio-only.mpg"
    source.write_bytes(b"audio-only")
    with factory() as session, session.begin():
        library = RefinerLibraryRow(
            name="Movies",
            media_scope="movie",
            watched_folder=str(watched),
            output_folder=str(tmp_path / "output"),
            rejected_file_action="delete_file",
        )
        session.add(library)
        session.flush()
        library_id = int(library.id)
        session.add(
            RefinerFileRow(
                library_id=library_id,
                relative_path=source.name,
                status=RefinerFileStatus.PROCESSING.value,
                status_reason="Processing",
            )
        )

    result: dict[str, Any] = {
        "ok": False,
        "outcome": "failed_before_execution",
        "relative_media_path": source.name,
        "inspected_source_path": str(source.resolve()),
        "refiner_watched_folder_resolved": str(watched.resolve()),
        "rejection_kind": "no_video_stream",
        "reason": "This file contains no video, so it was rejected before any output was written.",
        "rejected_file_action": "delete_file",
        "rejected_cleanup_status": "pending",
        "rejected_cleanup_detail": "The deletion decision was recorded first.",
    }
    handler_mod._apply_file_outcome_state(
        factory,
        result=result,
        library_id=library_id,
        media_scope="movie",
    )
    handler_mod._record(factory, payload=result)
    assert source.exists()

    handler_mod._finish_rejected_input_cleanup(
        factory,
        result=result,
        library_id=library_id,
        media_scope="movie",
    )

    assert not source.exists()
    assert result["rejected_cleanup_status"] == "deleted"
    with factory() as session:
        row = session.scalars(select(RefinerFileRow)).one()
        assert row.status == RefinerFileStatus.SKIPPED.value
        assert row.failure_attempts == 0
        assert "deleted the rejected file" in row.status_reason
