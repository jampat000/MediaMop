"""Refiner watched-folder remux scan dispatch: refiner_jobs + handler + activity (isolated SQLite)."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from mediamop.core.config import MediaMopSettings
from mediamop.core.db import Base
from mediamop.modules.refiner.jobs_model import RefinerJob, RefinerJobStatus
from mediamop.modules.refiner.jobs_ops import refiner_enqueue_or_get_job
from mediamop.modules.refiner.refiner_job_handlers import build_refiner_job_handlers
from mediamop.modules.refiner.refiner_operator_settings_model import RefinerOperatorSettingsRow
from mediamop.modules.refiner.refiner_path_settings_model import RefinerPathSettingsRow
from mediamop.modules.refiner.refiner_watched_folder_remux_scan_dispatch_job_kinds import (
    REFINER_WATCHED_FOLDER_REMUX_SCAN_DISPATCH_JOB_KIND,
)
from mediamop.modules.refiner.worker_loop import process_one_refiner_job
from mediamop.platform.activity import constants as C
from mediamop.platform.activity.models import ActivityEvent

import mediamop.modules.refiner.jobs_model  # noqa: F401
import mediamop.modules.refiner.refiner_path_settings_model  # noqa: F401
import mediamop.platform.activity.models  # noqa: F401
import mediamop.platform.auth.models  # noqa: F401


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

    def _fake_fetch(_session: Session, _settings: MediaMopSettings):
        return fake_rad, [], None, None

    t0 = datetime(2026, 4, 12, 12, 0, 0, tzinfo=timezone.utc)

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
        "mediamop.modules.refiner.refiner_watched_folder_remux_scan_dispatch_handlers.fetch_radarr_and_sonarr_queue_rows_for_scan",
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

        ev = s.scalars(
            select(ActivityEvent).where(
                ActivityEvent.event_type == C.REFINER_WATCHED_FOLDER_REMUX_SCAN_DISPATCH_COMPLETED,
            ),
        ).first()
        assert ev is not None
        detail = json.loads(ev.detail or "{}")
        assert detail.get("verdict_proceed") == 1
        assert detail.get("remux_jobs_enqueued") == 1
        assert detail.get("scan_result_label") == "Files added to Refiner"
        assert detail.get("scan_trigger") == "manual"


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

    def _fake_fetch(_session: Session, _settings: MediaMopSettings):
        return [], [], "Radarr not configured", "Sonarr not configured"

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
            dedupe_key="refiner.watched_folder.remux_scan_dispatch.v1:no-arr",
            job_kind=REFINER_WATCHED_FOLDER_REMUX_SCAN_DISPATCH_JOB_KIND,
            payload_json=json.dumps({"enqueue_remux_jobs": True}),
        )
        s.commit()

    handlers = build_refiner_job_handlers(settings, session_factory)
    with patch(
        "mediamop.modules.refiner.refiner_watched_folder_remux_scan_dispatch_handlers.fetch_radarr_and_sonarr_queue_rows_for_scan",
        side_effect=_fake_fetch,
    ):
        assert (
            process_one_refiner_job(
                session_factory,
                lease_owner="scan-test",
                job_handlers=handlers,
                now=datetime(2026, 4, 12, 12, 0, 0, tzinfo=timezone.utc),
                lease_seconds=3600,
            )
            == "processed"
        )

    with session_factory() as s:
        remux = [
            j
            for j in s.scalars(select(RefinerJob)).all()
            if j.job_kind == "refiner.file.remux_pass.v1"
        ]
        assert len(remux) == 1
        body = json.loads(remux[0].payload_json or "{}")
        assert body.get("relative_media_path") == "Standalone Movie 2026.mkv"
        ev = s.scalars(
            select(ActivityEvent).where(
                ActivityEvent.event_type == C.REFINER_WATCHED_FOLDER_REMUX_SCAN_DISPATCH_COMPLETED,
            ),
        ).first()
        assert ev is not None
        detail = json.loads(ev.detail or "{}")
        assert detail.get("verdict_proceed") == 1
        assert detail.get("remux_jobs_enqueued") == 1
        assert detail.get("user_message") == "1 file was added to Refiner for processing."


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
        "mediamop.modules.refiner.refiner_watched_folder_remux_scan_dispatch_handlers.fetch_radarr_and_sonarr_queue_rows_for_scan",
        return_value=([], [], None, None),
    ):
        assert (
            process_one_refiner_job(
                session_factory,
                lease_owner="scan-test",
                job_handlers=handlers,
                now=datetime(2026, 4, 12, 12, 0, 0, tzinfo=timezone.utc),
                lease_seconds=3600,
            )
            == "processed"
        )

    with session_factory() as s:
        assert (
            s.scalar(
                select(ActivityEvent).where(
                    ActivityEvent.event_type == C.REFINER_WATCHED_FOLDER_REMUX_SCAN_DISPATCH_COMPLETED,
                ),
            )
            is None
        )
