"""Periodic watched-folder scan dispatch enqueue — Refiner-local duplicate guard + prerequisites."""

from __future__ import annotations

import json
from dataclasses import replace
from types import SimpleNamespace

from sqlalchemy import delete, select, update

from mediamop.core.config import MediaMopSettings
from mediamop.core.db import create_db_engine, create_session_factory
from mediamop.modules.refiner.jobs_model import RefinerJob, RefinerJobStatus
from mediamop.modules.refiner.refiner_path_settings_model import RefinerPathSettingsRow
from mediamop.modules.refiner.refiner_watched_folder_remux_scan_dispatch_enqueue import (
    refiner_watched_folder_remux_scan_dispatch_queue_has_active_scan,
    try_enqueue_periodic_watched_folder_remux_scan_dispatch,
)
from mediamop.modules.refiner.refiner_watched_folder_remux_scan_dispatch_job_kinds import (
    REFINER_WATCHED_FOLDER_REMUX_SCAN_DISPATCH_JOB_KIND,
)
from mediamop.modules.refiner.refiner_watched_folder_remux_scan_dispatch_periodic_enqueue import (
    _watched_folder_scan_interval_seconds,
)

import mediamop.modules.refiner.jobs_model  # noqa: F401
import mediamop.modules.refiner.refiner_path_settings_model  # noqa: F401
import mediamop.platform.activity.models  # noqa: F401
import mediamop.platform.auth.models  # noqa: F401


def _fac():
    settings = MediaMopSettings.load()
    eng = create_db_engine(settings)
    return create_session_factory(eng)


def _settings_on() -> MediaMopSettings:
    base = MediaMopSettings.load()
    return replace(
        base,
        refiner_watched_folder_remux_scan_dispatch_schedule_enabled=True,
        refiner_watched_folder_remux_scan_dispatch_schedule_interval_seconds=3600,
        refiner_watched_folder_remux_scan_dispatch_periodic_enqueue_remux_jobs=True,
    )


def test_periodic_scheduler_uses_library_watched_folder_interval() -> None:
    row = SimpleNamespace(
        movie_watched_folder_check_interval_seconds=20,
        tv_watched_folder_check_interval_seconds=40,
    )
    assert _watched_folder_scan_interval_seconds(row, media_scope="movie") == 20
    assert _watched_folder_scan_interval_seconds(row, media_scope="tv") == 40


def test_queue_has_active_scan_detects_pending_and_leased_per_scope() -> None:
    fac = _fac()
    with fac() as db:
        db.execute(delete(RefinerJob))
        db.add(
            RefinerJob(
                dedupe_key="wf-scan-active-1",
                job_kind=REFINER_WATCHED_FOLDER_REMUX_SCAN_DISPATCH_JOB_KIND,
                status=RefinerJobStatus.PENDING.value,
            ),
        )
        db.commit()
    with fac() as db:
        assert refiner_watched_folder_remux_scan_dispatch_queue_has_active_scan(db, media_scope="movie") is True
        assert refiner_watched_folder_remux_scan_dispatch_queue_has_active_scan(db, media_scope="tv") is False

    tv_payload = json.dumps({"media_scope": "tv", "scan_trigger": "manual"})
    with fac() as db:
        db.execute(delete(RefinerJob))
        db.add(
            RefinerJob(
                dedupe_key="wf-scan-active-tv",
                job_kind=REFINER_WATCHED_FOLDER_REMUX_SCAN_DISPATCH_JOB_KIND,
                status=RefinerJobStatus.PENDING.value,
                payload_json=tv_payload,
            ),
        )
        db.commit()
    with fac() as db:
        assert refiner_watched_folder_remux_scan_dispatch_queue_has_active_scan(db, media_scope="movie") is False
        assert refiner_watched_folder_remux_scan_dispatch_queue_has_active_scan(db, media_scope="tv") is True

    with fac() as db:
        db.execute(delete(RefinerJob))
        db.add(
            RefinerJob(
                dedupe_key="wf-scan-active-2",
                job_kind=REFINER_WATCHED_FOLDER_REMUX_SCAN_DISPATCH_JOB_KIND,
                status=RefinerJobStatus.LEASED.value,
                lease_owner="w",
                attempt_count=1,
            ),
        )
        db.commit()
    with fac() as db:
        assert refiner_watched_folder_remux_scan_dispatch_queue_has_active_scan(db, media_scope="movie") is True
        assert refiner_watched_folder_remux_scan_dispatch_queue_has_active_scan(db, media_scope="tv") is False

    with fac() as db:
        db.execute(delete(RefinerJob))
        db.add(
            RefinerJob(
                dedupe_key="wf-scan-done",
                job_kind=REFINER_WATCHED_FOLDER_REMUX_SCAN_DISPATCH_JOB_KIND,
                status=RefinerJobStatus.COMPLETED.value,
                attempt_count=1,
            ),
        )
        db.commit()
    with fac() as db:
        assert refiner_watched_folder_remux_scan_dispatch_queue_has_active_scan(db, media_scope="movie") is False
        assert refiner_watched_folder_remux_scan_dispatch_queue_has_active_scan(db, media_scope="tv") is False


def test_try_enqueue_periodic_skips_when_schedule_disabled() -> None:
    fac = _fac()
    base = MediaMopSettings.load()
    off = replace(base, refiner_watched_folder_remux_scan_dispatch_schedule_enabled=False)
    with fac() as db:
        ins, skip = try_enqueue_periodic_watched_folder_remux_scan_dispatch(db, off)
        db.rollback()
    assert ins is False
    assert skip == "schedule_disabled"


def test_try_enqueue_periodic_skips_when_active_scan_exists() -> None:
    fac = _fac()
    settings = _settings_on()
    with fac() as db:
        db.execute(delete(RefinerJob))
        db.execute(
            update(RefinerPathSettingsRow)
            .where(RefinerPathSettingsRow.id == 1)
            .values(
                refiner_watched_folder=None,
                refiner_output_folder="",
                refiner_tv_watched_folder=None,
                refiner_tv_output_folder=None,
            ),
        )
        db.add(
            RefinerJob(
                dedupe_key="wf-scan-block",
                job_kind=REFINER_WATCHED_FOLDER_REMUX_SCAN_DISPATCH_JOB_KIND,
                status=RefinerJobStatus.PENDING.value,
            ),
        )
        db.commit()
    with fac() as db:
        ins, skip = try_enqueue_periodic_watched_folder_remux_scan_dispatch(db, settings)
        db.rollback()
    assert ins is False
    assert skip == "no_saved_watched_folder"


def test_try_enqueue_periodic_enqueues_tv_when_movie_scope_blocked(tmp_path) -> None:
    fac = _fac()
    settings = _settings_on()
    for name in ("mwatch", "mout", "twatch", "tout"):
        tmp_path.joinpath(name).mkdir()
    mw = str(tmp_path / "mwatch")
    mo = str(tmp_path / "mout")
    tw = str(tmp_path / "twatch")
    to = str(tmp_path / "tout")

    block_payload = json.dumps({"media_scope": "movie", "scan_trigger": "manual"})
    with fac() as db:
        db.execute(delete(RefinerJob))
        db.add(
            RefinerJob(
                dedupe_key="wf-scan-block-movie",
                job_kind=REFINER_WATCHED_FOLDER_REMUX_SCAN_DISPATCH_JOB_KIND,
                status=RefinerJobStatus.PENDING.value,
                payload_json=block_payload,
            ),
        )
        db.execute(
            update(RefinerPathSettingsRow)
            .where(RefinerPathSettingsRow.id == 1)
            .values(
                refiner_watched_folder=mw,
                refiner_output_folder=mo,
                refiner_tv_watched_folder=tw,
                refiner_tv_output_folder=to,
            ),
        )
        db.commit()
    try:
        with fac() as db:
            ins, skip = try_enqueue_periodic_watched_folder_remux_scan_dispatch(db, settings)
            db.commit()
        assert ins is True
        assert skip is None
        with fac() as db:
            rows = db.scalars(
                select(RefinerJob).where(RefinerJob.job_kind == REFINER_WATCHED_FOLDER_REMUX_SCAN_DISPATCH_JOB_KIND),
            ).all()
        assert len(rows) == 2
        periodic_rows = [r for r in rows if json.loads(r.payload_json or "{}").get("scan_trigger") == "periodic"]
        assert len(periodic_rows) == 1
        assert json.loads(periodic_rows[0].payload_json or "{}").get("media_scope") == "tv"
    finally:
        with fac() as db:
            db.execute(delete(RefinerJob))
            db.execute(
                update(RefinerPathSettingsRow)
                .where(RefinerPathSettingsRow.id == 1)
                .values(
                    refiner_watched_folder=None,
                    refiner_output_folder="",
                    refiner_tv_watched_folder=None,
                    refiner_tv_output_folder=None,
                ),
            )
            db.commit()


def test_try_enqueue_periodic_inserts_movie_and_tv_when_both_scopes_ready(tmp_path) -> None:
    fac = _fac()
    settings = _settings_on()
    for name in ("mwatch", "mout", "twatch", "tout"):
        tmp_path.joinpath(name).mkdir()
    mw = str(tmp_path / "mwatch")
    mo = str(tmp_path / "mout")
    tw = str(tmp_path / "twatch")
    to = str(tmp_path / "tout")
    with fac() as db:
        db.execute(delete(RefinerJob))
        db.execute(
            update(RefinerPathSettingsRow)
            .where(RefinerPathSettingsRow.id == 1)
            .values(
                refiner_watched_folder=mw,
                refiner_output_folder=mo,
                refiner_tv_watched_folder=tw,
                refiner_tv_output_folder=to,
            ),
        )
        db.commit()
    try:
        with fac() as db:
            ins, skip = try_enqueue_periodic_watched_folder_remux_scan_dispatch(db, settings)
            db.commit()
        assert ins is True
        assert skip is None
        with fac() as db:
            rows = db.scalars(
                select(RefinerJob).where(RefinerJob.job_kind == REFINER_WATCHED_FOLDER_REMUX_SCAN_DISPATCH_JOB_KIND),
            ).all()
        assert len(rows) == 2
        scopes = {json.loads(r.payload_json or "{}").get("media_scope", "movie") for r in rows}
        assert scopes == {"movie", "tv"}
        for r in rows:
            body = json.loads(r.payload_json or "{}")
            assert body.get("scan_trigger") == "periodic"
            assert body.get("enqueue_remux_jobs") is True
    finally:
        with fac() as db:
            db.execute(delete(RefinerJob))
            db.execute(
                update(RefinerPathSettingsRow)
                .where(RefinerPathSettingsRow.id == 1)
                .values(
                    refiner_watched_folder=None,
                    refiner_output_folder="",
                    refiner_tv_watched_folder=None,
                    refiner_tv_output_folder=None,
                ),
            )
            db.commit()


def test_try_enqueue_periodic_inserts_when_prerequisites_met(tmp_path) -> None:
    fac = _fac()
    settings = _settings_on()
    watched = str(tmp_path / "watch")
    tmp_path.joinpath("watch").mkdir()
    out = str(tmp_path / "out")
    tmp_path.joinpath("out").mkdir()
    with fac() as db:
        db.execute(delete(RefinerJob))
        db.execute(
            update(RefinerPathSettingsRow)
            .where(RefinerPathSettingsRow.id == 1)
            .values(
                refiner_watched_folder=watched,
                refiner_output_folder=out,
            ),
        )
        db.commit()
    try:
        with fac() as db:
            ins, skip = try_enqueue_periodic_watched_folder_remux_scan_dispatch(db, settings)
            db.commit()
        assert ins is True
        assert skip is None
        with fac() as db:
            row = db.scalars(
                select(RefinerJob).where(RefinerJob.job_kind == REFINER_WATCHED_FOLDER_REMUX_SCAN_DISPATCH_JOB_KIND),
            ).first()
            assert row is not None
            assert row.status == RefinerJobStatus.PENDING.value
            body = json.loads(row.payload_json or "{}")
            assert body.get("scan_trigger") == "periodic"
            assert body.get("media_scope") == "movie"
    finally:
        with fac() as db:
            db.execute(delete(RefinerJob))
            db.execute(
                update(RefinerPathSettingsRow)
                .where(RefinerPathSettingsRow.id == 1)
                .values(
                    refiner_watched_folder=None,
                    refiner_output_folder="",
                ),
            )
            db.commit()
