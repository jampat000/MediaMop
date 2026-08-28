"""Refiner watched-folder remux scan dispatch: refiner_jobs + handler (isolated SQLite)."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

import mediamop.modules.refiner.jobs_model  # noqa: F401
import mediamop.modules.refiner.refiner_path_settings_model  # noqa: F401
import mediamop.platform.activity.models  # noqa: F401
import mediamop.platform.auth.models  # noqa: F401
from mediamop.core.config import MediaMopSettings
from mediamop.core.db import Base
from mediamop.modules.refiner.jobs_model import RefinerJob, RefinerJobStatus
from mediamop.modules.refiner.jobs_ops import refiner_enqueue_or_get_job
from mediamop.modules.refiner.manager_queue_signals import report_for_signals
from mediamop.modules.refiner.refiner_job_handlers import build_refiner_job_handlers
from mediamop.modules.refiner.refiner_operator_settings_model import RefinerOperatorSettingsRow
from mediamop.modules.refiner.refiner_path_settings_model import RefinerPathSettingsRow
from mediamop.modules.refiner.refiner_watched_folder_remux_scan_dispatch_job_kinds import (
    REFINER_WATCHED_FOLDER_REMUX_SCAN_DISPATCH_JOB_KIND,
)
from mediamop.modules.refiner.worker_loop import process_one_refiner_job
from mediamop.platform.activity.models import ActivityEvent
from tests.manager_signal_helpers import reported


@pytest.fixture
def scan_engine(tmp_path: Path):
    url = f"sqlite:///{tmp_path / 'refiner_watched_scan.sqlite'}"
    engine = create_engine(
        url,
        connect_args={"check_same_thread": False, "timeout": 30.0},
        future=True,
    )
    Base.metadata.create_all(engine)
    return engine


@pytest.fixture
def session_factory(scan_engine):
    return sessionmaker(
        bind=scan_engine,
        class_=Session,
        autoflush=False,
        autocommit=False,
        expire_on_commit=False,
        future=True,
    )


def test_scan_handler_enqueues_remux_when_requested(
    session_factory,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MEDIAMOP_REFINER_WATCHED_FOLDER_MIN_FILE_AGE_SECONDS", "0")
    monkeypatch.setenv("MEDIAMOP_ARR_RADARR_BASE_URL", "http://127.0.0.1:9")
    monkeypatch.setenv("MEDIAMOP_ARR_RADARR_API_KEY", "k")
    settings = MediaMopSettings.load()

    watch = tmp_path / "watch"
    watch.mkdir()
    out = tmp_path / "out"
    out.mkdir()
    mkv = watch / "Gate Test 2001.mkv"
    mkv.write_bytes(b"x")

    fake_rad = [
        {
            "status": "importPending",
            "outputPath": str(mkv.resolve()),
            "movie": {"title": "Gate Test", "year": 2001},
        },
    ]

    def _fake_fetch(_session: Session, _settings: MediaMopSettings, *, media_scope: str):
        signals = (reported(fake_rad, name="Main"),)
        return signals, report_for_signals(signals)

    t0 = datetime(2026, 4, 12, 12, 0, 0, tzinfo=UTC)

    with session_factory() as s:
        s.merge(
            RefinerPathSettingsRow(
                id=1,
                refiner_watched_folder=str(watch.resolve()),
                refiner_work_folder=None,
                refiner_output_folder=str(out.resolve()),
            ),
        )
        s.merge(
            RefinerOperatorSettingsRow(
                id=1,
                min_file_age_seconds=0,
                refiner_min_input_file_size_mb=0,
                minimum_free_disk_space_mb=0,
            )
        )
        s.commit()

    payload = {"enqueue_remux_jobs": True}
    with session_factory() as s:
        refiner_enqueue_or_get_job(
            s,
            dedupe_key="refiner.watched_folder.remux_scan_dispatch.v1:lane-test",
            job_kind=REFINER_WATCHED_FOLDER_REMUX_SCAN_DISPATCH_JOB_KIND,
            payload_json=json.dumps(payload),
        )
        s.commit()

    handlers = build_refiner_job_handlers(settings, session_factory)
    with patch(
        "mediamop.modules.refiner.refiner_watched_folder_remux_scan_dispatch_handlers.fetch_manager_queue_signals_for_scan",
        side_effect=_fake_fetch,
    ):
        assert (
            process_one_refiner_job(
                session_factory,
                lease_owner="scan-test",
                job_handlers=handlers,
                now=t0,
                lease_seconds=3600,
            )
            == "processed"
        )

    with session_factory() as s:
        jobs = s.scalars(select(RefinerJob)).all()
        assert len(jobs) == 2
        kinds = {j.job_kind for j in jobs}
        assert REFINER_WATCHED_FOLDER_REMUX_SCAN_DISPATCH_JOB_KIND in kinds
        remux = [j for j in jobs if j.job_kind == "refiner.file.remux_pass.v1"]
        assert len(remux) == 1
        assert remux[0].status == RefinerJobStatus.PENDING.value
        body = json.loads(remux[0].payload_json or "{}")
        assert body.get("relative_media_path") == "Gate Test 2001.mkv"
        assert "dry_run" not in body

        assert s.scalar(select(ActivityEvent)) is None


def test_scan_handler_enqueues_remux_without_arr_connections(
    session_factory,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MEDIAMOP_REFINER_WATCHED_FOLDER_MIN_FILE_AGE_SECONDS", "0")
    settings = MediaMopSettings.load()

    watch = tmp_path / "watch_no_arr"
    watch.mkdir()
    out = tmp_path / "out_no_arr"
    out.mkdir()
    mkv = watch / "Standalone Movie 2026.mkv"
    mkv.write_bytes(b"x")

    def _fake_fetch(_session: Session, _settings: MediaMopSettings, *, media_scope: str):
        # Nothing connected at all: the scan still runs, on the file-settling gates alone.
        return (), report_for_signals(())

    with session_factory() as s:
        s.merge(
            RefinerPathSettingsRow(
                id=1,
                refiner_watched_folder=str(watch.resolve()),
                refiner_work_folder=None,
                refiner_output_folder=str(out.resolve()),
            ),
        )
        s.merge(
            RefinerOperatorSettingsRow(
                id=1,
                min_file_age_seconds=0,
                refiner_min_input_file_size_mb=0,
                minimum_free_disk_space_mb=0,
            )
        )
        s.commit()

    with session_factory() as s:
        refiner_enqueue_or_get_job(
            s,
            dedupe_key="refiner.watched_folder.remux_scan_dispatch.v1:no-arr",
            job_kind=REFINER_WATCHED_FOLDER_REMUX_SCAN_DISPATCH_JOB_KIND,
            payload_json=json.dumps({"enqueue_remux_jobs": True}),
        )
        s.commit()

    handlers = build_refiner_job_handlers(settings, session_factory)
    with patch(
        "mediamop.modules.refiner.refiner_watched_folder_remux_scan_dispatch_handlers.fetch_manager_queue_signals_for_scan",
        side_effect=_fake_fetch,
    ):
        assert (
            process_one_refiner_job(
                session_factory,
                lease_owner="scan-test",
                job_handlers=handlers,
                now=datetime(2026, 4, 12, 12, 0, 0, tzinfo=UTC),
                lease_seconds=3600,
            )
            == "processed"
        )

    with session_factory() as s:
        remux = [j for j in s.scalars(select(RefinerJob)).all() if j.job_kind == "refiner.file.remux_pass.v1"]
        assert len(remux) == 1
        body = json.loads(remux[0].payload_json or "{}")
        assert body.get("relative_media_path") == "Standalone Movie 2026.mkv"
        assert s.scalar(select(ActivityEvent)) is None


def test_scan_handler_skips_file_when_previous_success_output_still_exists(
    session_factory,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MEDIAMOP_REFINER_WATCHED_FOLDER_MIN_FILE_AGE_SECONDS", "0")
    settings = MediaMopSettings.load()

    watch = tmp_path / "watch_existing_output"
    watch.mkdir()
    out = tmp_path / "out_existing_output"
    out.mkdir()
    release = watch / "Locked Source 2026"
    release.mkdir()
    mkv = release / "Locked Source 2026.mkv"
    mkv.write_bytes(b"source-still-locked")
    output = out / "Locked Source 2026" / "Locked Source 2026.mkv"
    output.parent.mkdir(parents=True)
    output.write_bytes(b"already-written")

    with session_factory() as s:
        s.merge(
            RefinerPathSettingsRow(
                id=1,
                refiner_watched_folder=str(watch.resolve()),
                refiner_work_folder=None,
                refiner_output_folder=str(out.resolve()),
            ),
        )
        s.merge(
            RefinerOperatorSettingsRow(
                id=1,
                min_file_age_seconds=0,
                refiner_min_input_file_size_mb=0,
                minimum_free_disk_space_mb=0,
            )
        )
        s.add(
            ActivityEvent(
                module="refiner",
                event_type="refiner.file_remux_pass_completed",
                title="Locked Source 2026.mkv was processed successfully",
                detail=json.dumps(
                    {
                        "ok": True,
                        "relative_media_path": "Locked Source 2026/Locked Source 2026.mkv",
                        "media_scope": "movie",
                        "output_file": str(output.resolve()),
                        "source_deleted_after_success": False,
                        "source_folder_skip_reason": "file is locked",
                    },
                ),
            ),
        )
        s.commit()

    with session_factory() as s:
        refiner_enqueue_or_get_job(
            s,
            dedupe_key="refiner.watched_folder.remux_scan_dispatch.v1:existing-output",
            job_kind=REFINER_WATCHED_FOLDER_REMUX_SCAN_DISPATCH_JOB_KIND,
            payload_json=json.dumps({"enqueue_remux_jobs": True}),
        )
        s.commit()

    handlers = build_refiner_job_handlers(settings, session_factory)
    with patch(
        "mediamop.modules.refiner.refiner_watched_folder_remux_scan_dispatch_handlers.fetch_manager_queue_signals_for_scan",
        return_value=((), report_for_signals(())),
    ):
        assert (
            process_one_refiner_job(
                session_factory,
                lease_owner="scan-test",
                job_handlers=handlers,
                now=datetime(2026, 4, 12, 12, 0, 0, tzinfo=UTC),
                lease_seconds=3600,
            )
            == "processed"
        )

    with session_factory() as s:
        remux = [j for j in s.scalars(select(RefinerJob)).all() if j.job_kind == "refiner.file.remux_pass.v1"]
        assert remux == []
    assert watch.exists()
    assert not release.exists()


def test_scan_handler_does_not_record_activity_when_no_files_are_queued(
    session_factory,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MEDIAMOP_REFINER_WATCHED_FOLDER_MIN_FILE_AGE_SECONDS", "0")
    settings = MediaMopSettings.load()

    watch = tmp_path / "watch_no_activity"
    watch.mkdir()
    out = tmp_path / "out_no_activity"
    out.mkdir()
    (watch / "Already Checked 2026.mkv").write_bytes(b"x")

    with session_factory() as s:
        s.merge(
            RefinerPathSettingsRow(
                id=1,
                refiner_watched_folder=str(watch.resolve()),
                refiner_work_folder=None,
                refiner_output_folder=str(out.resolve()),
            ),
        )
        s.merge(RefinerOperatorSettingsRow(id=1, min_file_age_seconds=0))
        s.commit()

    with session_factory() as s:
        refiner_enqueue_or_get_job(
            s,
            dedupe_key="refiner.watched_folder.remux_scan_dispatch.v1:no-activity",
            job_kind=REFINER_WATCHED_FOLDER_REMUX_SCAN_DISPATCH_JOB_KIND,
            payload_json=json.dumps({"enqueue_remux_jobs": False}),
        )
        s.commit()

    handlers = build_refiner_job_handlers(settings, session_factory)
    with patch(
        "mediamop.modules.refiner.refiner_watched_folder_remux_scan_dispatch_handlers.fetch_manager_queue_signals_for_scan",
        return_value=((reported([]),), report_for_signals((reported([]),))),
    ):
        assert (
            process_one_refiner_job(
                session_factory,
                lease_owner="scan-test",
                job_handlers=handlers,
                now=datetime(2026, 4, 12, 12, 0, 0, tzinfo=UTC),
                lease_seconds=3600,
            )
            == "processed"
        )

    with session_factory() as s:
        assert s.scalar(select(ActivityEvent)) is None


def _seed_library(session_factory, *, watch: Path, out: Path, **overrides) -> None:
    """A library row, so the file-state gates in the handler actually run.

    The lane tests above predate libraries and resolve to none, which makes the whole
    state block a no-op for them. These two need it.
    """

    from mediamop.modules.refiner.refiner_library_model import RefinerLibraryRow

    with session_factory() as s:
        s.add(
            RefinerLibraryRow(
                name="Movies",
                media_scope="movie",
                enabled=True,
                display_order=0,
                watched_folder=str(watch.resolve()),
                output_folder=str(out.resolve()),
                min_file_age_seconds=0,
                hold_minutes=0,
                schedule_enabled=False,
                file_detection_interval_seconds=overrides.pop("file_detection_interval_seconds", 30),
                **overrides,
            )
        )
        s.commit()


def _run_scan(session_factory, settings, *, dedupe: str, now: datetime) -> str:
    def _fake_fetch(_session: Session, _settings: MediaMopSettings, *, media_scope: str):
        signals = (reported([], name="Main"),)
        return signals, report_for_signals(signals)

    with session_factory() as s:
        refiner_enqueue_or_get_job(
            s,
            dedupe_key=f"refiner.watched_folder.remux_scan_dispatch.v1:{dedupe}",
            job_kind=REFINER_WATCHED_FOLDER_REMUX_SCAN_DISPATCH_JOB_KIND,
            payload_json=json.dumps({"enqueue_remux_jobs": True}),
        )
        s.commit()

    handlers = build_refiner_job_handlers(settings, session_factory)
    with patch(
        "mediamop.modules.refiner.refiner_watched_folder_remux_scan_dispatch_handlers."
        "fetch_manager_queue_signals_for_scan",
        side_effect=_fake_fetch,
    ):
        return process_one_refiner_job(
            session_factory,
            lease_owner="settling-test",
            job_handlers=handlers,
            now=now,
            lease_seconds=3600,
        )


def _remux_jobs(session_factory) -> list[RefinerJob]:
    with session_factory() as s:
        return [j for j in s.scalars(select(RefinerJob)).all() if j.job_kind == "refiner.file.remux_pass.v1"]


def test_a_file_still_settling_is_never_enqueued(
    session_factory,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The first sighting of a file is one observation, and one observation proves nothing.

    An mtime threshold would have queued this immediately with the age gate at zero. Size
    settling holds it, and the operator can see why (#335).
    """

    monkeypatch.setenv("MEDIAMOP_REFINER_WATCHED_FOLDER_MIN_FILE_AGE_SECONDS", "0")
    settings = MediaMopSettings.load()

    watch = tmp_path / "watch"
    watch.mkdir()
    out = tmp_path / "out"
    out.mkdir()
    (watch / "Gate Test 2001.mkv").write_bytes(b"x" * 1024)

    with session_factory() as s:
        s.merge(
            RefinerPathSettingsRow(
                id=1,
                refiner_watched_folder=str(watch.resolve()),
                refiner_work_folder=None,
                refiner_output_folder=str(out.resolve()),
            ),
        )
        s.merge(
            RefinerOperatorSettingsRow(
                id=1, min_file_age_seconds=0, refiner_min_input_file_size_mb=0, minimum_free_disk_space_mb=0
            )
        )
        s.commit()
    _seed_library(session_factory, watch=watch, out=out)

    assert _run_scan(session_factory, settings, dedupe="first", now=datetime(2026, 4, 12, 12, 0, tzinfo=UTC)) == (
        "processed"
    )

    assert _remux_jobs(session_factory) == []

    from mediamop.modules.refiner.refiner_file_state_model import RefinerFileRow, RefinerFileStatus

    with session_factory() as s:
        row = s.scalars(select(RefinerFileRow)).one()
        assert row.status == RefinerFileStatus.ON_HOLD.value
        assert row.relative_path == "Gate Test 2001.mkv"
        assert row.size_bytes == 1024
        # The reason is the point: the operator can see this is a wait, not a failure.
        assert "writing" in row.status_reason or "only just found" in row.status_reason
        assert row.hold_until is not None


def test_a_file_whose_size_has_held_still_is_enqueued_on_the_next_scan(
    session_factory,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MEDIAMOP_REFINER_WATCHED_FOLDER_MIN_FILE_AGE_SECONDS", "0")
    settings = MediaMopSettings.load()

    watch = tmp_path / "watch"
    watch.mkdir()
    out = tmp_path / "out"
    out.mkdir()
    (watch / "Gate Test 2001.mkv").write_bytes(b"x" * 1024)

    with session_factory() as s:
        s.merge(
            RefinerPathSettingsRow(
                id=1,
                refiner_watched_folder=str(watch.resolve()),
                refiner_work_folder=None,
                refiner_output_folder=str(out.resolve()),
            ),
        )
        s.merge(
            RefinerOperatorSettingsRow(
                id=1, min_file_age_seconds=0, refiner_min_input_file_size_mb=0, minimum_free_disk_space_mb=0
            )
        )
        s.commit()
    _seed_library(session_factory, watch=watch, out=out)

    _run_scan(session_factory, settings, dedupe="first", now=datetime(2026, 4, 12, 12, 0, tzinfo=UTC))
    assert _remux_jobs(session_factory) == []

    from mediamop.modules.refiner.refiner_file_state_model import RefinerFileRow

    # Backdate the observation, which is exactly what the next scan sees once the
    # detection interval has passed with the size unchanged.
    with session_factory() as s:
        row = s.scalars(select(RefinerFileRow)).one()
        row.size_changed_at = datetime.now(UTC) - timedelta(seconds=120)
        s.commit()

    assert _run_scan(session_factory, settings, dedupe="second", now=datetime(2026, 4, 12, 12, 5, tzinfo=UTC)) == (
        "processed"
    )

    remux = _remux_jobs(session_factory)
    assert len(remux) == 1
    assert json.loads(remux[0].payload_json or "{}").get("relative_media_path") == "Gate Test 2001.mkv"
