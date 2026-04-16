"""Tests for Refiner TV season-folder cleanup (Pass 1b)."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

import pytest
from dataclasses import replace
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from mediamop.core.config import MediaMopSettings
from mediamop.core.db import Base
from mediamop.modules.refiner.jobs_model import RefinerJob, RefinerJobStatus
from mediamop.modules.refiner.refiner_file_remux_pass_job_kinds import REFINER_FILE_REMUX_PASS_JOB_KIND
from mediamop.modules.refiner.refiner_file_remux_pass_visibility import (
    REMUX_PASS_OUTCOME_LIVE_OUTPUT_WRITTEN,
    REMUX_PASS_OUTCOME_LIVE_SKIPPED_NOT_REQUIRED,
)
from mediamop.modules.refiner.refiner_path_settings_service import RefinerPathRuntime
from mediamop.modules.refiner.refiner_tv_season_folder_cleanup import (
    get_tv_episode_set_media_files,
    handle_tv_cleanup_after_success,
)
from mediamop.platform.activity import constants as activity_c
from mediamop.platform.activity.models import ActivityEvent

import mediamop.modules.refiner.jobs_model  # noqa: F401
import mediamop.platform.activity.models  # noqa: F401


def _sqlite_session(tmp_path: Path) -> tuple[sessionmaker[Session], Session]:
    url = f"sqlite:///{tmp_path / 'tv.sqlite'}"
    engine = create_engine(url, connect_args={"check_same_thread": False}, future=True)
    Base.metadata.create_all(engine)
    fac = sessionmaker(bind=engine, class_=Session, autoflush=False, autocommit=False, future=True)
    return fac, fac()


def _tv_runtime(*, watched: Path, out: Path, home: Path) -> RefinerPathRuntime:
    work = home / "w"
    work.mkdir(parents=True, exist_ok=True)
    return RefinerPathRuntime(
        watched_folder=str(watched.resolve()),
        output_folder=str(out.resolve()),
        work_folder_effective=str(work.resolve()),
        work_folder_is_default=False,
        preview_output_folder=str(out.resolve()),
    )


def test_episode_set_direct_children_only(tmp_path: Path) -> None:
    season = tmp_path / "S01"
    season.mkdir()
    (season / "a.mkv").write_bytes(b"x")
    (season / "b.mkv").write_bytes(b"x")
    subs = season / "Subs"
    subs.mkdir()
    (subs / "hidden.mkv").write_bytes(b"x")
    got = get_tv_episode_set_media_files(season_folder=season)
    assert {p.name for p in got} == {"a.mkv", "b.mkv"}


def test_tv_cleanup_skips_when_sonarr_unreachable(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _, session = _sqlite_session(tmp_path)
    home = tmp_path / "h"
    home.mkdir()
    watched = tmp_path / "tvw"
    watched.mkdir()
    out = tmp_path / "out"
    out.mkdir()
    sdir = watched / "Serie" / "S01"
    sdir.mkdir(parents=True)
    ep = sdir / "e.mkv"
    ep.write_bytes(b"x" * 500)
    (out / "Serie" / "S01").mkdir(parents=True)
    (out / "Serie" / "S01" / "e.mkv").write_bytes(b"y" * 100)

    def _boom(_s, _settings):
        return [], [], None, "connection refused"

    monkeypatch.setattr(
        "mediamop.modules.refiner.refiner_tv_season_folder_cleanup.fetch_radarr_and_sonarr_queue_rows_for_scan",
        _boom,
    )

    settings = replace(MediaMopSettings.load(), mediamop_home=str(home), refiner_watched_folder_min_file_age_seconds=0)
    rt = _tv_runtime(watched=watched, out=out, home=home)
    outd: dict = {}
    handle_tv_cleanup_after_success(
        session=session,
        settings=settings,
        path_runtime=rt,
        src=ep,
        watched_root=watched,
        out=outd,
        dry_run=False,
        min_file_age_seconds=0,
        current_job_id=99,
        remux_context={
            "ok": True,
            "dry_run": False,
            "outcome": REMUX_PASS_OUTCOME_LIVE_SKIPPED_NOT_REQUIRED,
            "relative_media_path": "Serie/S01/e.mkv",
        },
        final_output_file=out / "Serie" / "S01" / "e.mkv",
    )
    assert outd["tv_sonarr_unreachable"] is True
    assert outd["tv_season_folder_deleted"] is False
    assert sdir.exists()


def test_tv_cleanup_blocked_by_active_other_tv_job(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _, session = _sqlite_session(tmp_path)
    monkeypatch.setattr(
        "mediamop.modules.refiner.refiner_tv_season_folder_cleanup.fetch_radarr_and_sonarr_queue_rows_for_scan",
        lambda _s, _settings: ([], [], None, None),
    )
    home = tmp_path / "h"
    home.mkdir()
    watched = tmp_path / "tvw"
    watched.mkdir()
    out = tmp_path / "out"
    out.mkdir()
    sdir = watched / "Serie" / "S01"
    sdir.mkdir(parents=True)
    ep = sdir / "e.mkv"
    ep.write_bytes(b"x" * 500)
    (out / "Serie" / "S01").mkdir(parents=True)
    (out / "Serie" / "S01" / "e.mkv").write_bytes(b"y" * 100)

    session.add(
        RefinerJob(
            dedupe_key="k1",
            job_kind=REFINER_FILE_REMUX_PASS_JOB_KIND,
            payload_json=json.dumps({"relative_media_path": "Serie/S01/e.mkv", "dry_run": False, "media_scope": "tv"}),
            status=RefinerJobStatus.PENDING.value,
            max_attempts=3,
        ),
    )
    session.commit()

    settings = replace(MediaMopSettings.load(), mediamop_home=str(home), refiner_watched_folder_min_file_age_seconds=0)
    rt = _tv_runtime(watched=watched, out=out, home=home)
    outd: dict = {}
    handle_tv_cleanup_after_success(
        session=session,
        settings=settings,
        path_runtime=rt,
        src=ep,
        watched_root=watched,
        out=outd,
        dry_run=False,
        min_file_age_seconds=0,
        current_job_id=999,
        remux_context={
            "ok": True,
            "dry_run": False,
            "outcome": REMUX_PASS_OUTCOME_LIVE_SKIPPED_NOT_REQUIRED,
            "relative_media_path": "Serie/S01/e.mkv",
        },
        final_output_file=out / "Serie" / "S01" / "e.mkv",
    )
    assert "queued or running" in (outd.get("tv_season_folder_skip_reason") or "")
    assert outd["tv_season_folder_deleted"] is False


def test_tv_cleanup_not_blocked_by_movie_scope_job_same_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _, session = _sqlite_session(tmp_path)
    home = tmp_path / "h"
    home.mkdir()
    watched = tmp_path / "tvw"
    watched.mkdir()
    out = tmp_path / "out"
    out.mkdir()
    sdir = watched / "Serie" / "S01"
    sdir.mkdir(parents=True)
    ep = sdir / "e.mkv"
    ep.write_bytes(b"x" * 500)
    (out / "Serie" / "S01").mkdir(parents=True)
    (out / "Serie" / "S01" / "e.mkv").write_bytes(b"y" * 100)

    session.add(
        RefinerJob(
            dedupe_key="km",
            job_kind=REFINER_FILE_REMUX_PASS_JOB_KIND,
            payload_json=json.dumps({"relative_media_path": "Serie/S01/e.mkv", "dry_run": False, "media_scope": "movie"}),
            status=RefinerJobStatus.PENDING.value,
            max_attempts=3,
        ),
    )
    session.commit()

    settings = replace(MediaMopSettings.load(), mediamop_home=str(home), refiner_watched_folder_min_file_age_seconds=0)
    rt = _tv_runtime(watched=watched, out=out, home=home)
    outd: dict = {}

    def _ok_fetch(_s, _settings):
        return [], [], None, None

    monkeypatch.setattr(
        "mediamop.modules.refiner.refiner_tv_season_folder_cleanup.fetch_radarr_and_sonarr_queue_rows_for_scan",
        _ok_fetch,
    )
    handle_tv_cleanup_after_success(
        session=session,
        settings=settings,
        path_runtime=rt,
        src=ep,
        watched_root=watched,
        out=outd,
        dry_run=False,
        min_file_age_seconds=0,
        current_job_id=1,
        remux_context={
            "ok": True,
            "dry_run": False,
            "outcome": REMUX_PASS_OUTCOME_LIVE_SKIPPED_NOT_REQUIRED,
            "relative_media_path": "Serie/S01/e.mkv",
        },
        final_output_file=out / "Serie" / "S01" / "e.mkv",
    )
    assert outd["tv_season_folder_deleted"] is True
    assert not sdir.exists()


def test_tv_cleanup_dry_run_no_deletes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _, session = _sqlite_session(tmp_path)
    home = tmp_path / "h"
    home.mkdir()
    watched = tmp_path / "tvw"
    watched.mkdir()
    out = tmp_path / "out"
    out.mkdir()
    sdir = watched / "Serie" / "S01"
    sdir.mkdir(parents=True)
    ep = sdir / "e.mkv"
    ep.write_bytes(b"x" * 500)
    (out / "Serie" / "S01").mkdir(parents=True)
    (out / "Serie" / "S01" / "e.mkv").write_bytes(b"y" * 100)

    monkeypatch.setattr(
        "mediamop.modules.refiner.refiner_tv_season_folder_cleanup.fetch_radarr_and_sonarr_queue_rows_for_scan",
        lambda _s, _settings: ([], [], None, None),
    )

    settings = replace(MediaMopSettings.load(), mediamop_home=str(home), refiner_watched_folder_min_file_age_seconds=0)
    rt = _tv_runtime(watched=watched, out=out, home=home)
    outd: dict = {}
    handle_tv_cleanup_after_success(
        session=session,
        settings=settings,
        path_runtime=rt,
        src=ep,
        watched_root=watched,
        out=outd,
        dry_run=True,
        min_file_age_seconds=0,
        current_job_id=1,
        remux_context={
            "ok": True,
            "dry_run": True,
            "outcome": "dry_run_planned",
            "relative_media_path": "Serie/S01/e.mkv",
        },
        final_output_file=None,
    )
    assert outd["tv_season_folder_deleted"] is False
    assert ep.exists()


def test_tv_cleanup_season_equals_watched_root_skipped(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _, session = _sqlite_session(tmp_path)
    home = tmp_path / "h"
    home.mkdir()
    watched = tmp_path / "tvw"
    watched.mkdir()
    ep = watched / "e.mkv"
    ep.write_bytes(b"x" * 400)
    out = tmp_path / "out"
    out.mkdir()
    (out / "e.mkv").write_bytes(b"y" * 80)

    monkeypatch.setattr(
        "mediamop.modules.refiner.refiner_tv_season_folder_cleanup.fetch_radarr_and_sonarr_queue_rows_for_scan",
        lambda _s, _settings: ([], [], None, None),
    )

    settings = replace(MediaMopSettings.load(), mediamop_home=str(home), refiner_watched_folder_min_file_age_seconds=0)
    rt = _tv_runtime(watched=watched, out=out, home=home)
    outd: dict = {}
    handle_tv_cleanup_after_success(
        session=session,
        settings=settings,
        path_runtime=rt,
        src=ep,
        watched_root=watched,
        out=outd,
        dry_run=False,
        min_file_age_seconds=0,
        current_job_id=1,
        remux_context={
            "ok": True,
            "dry_run": False,
            "outcome": REMUX_PASS_OUTCOME_LIVE_SKIPPED_NOT_REQUIRED,
            "relative_media_path": "e.mkv",
        },
        final_output_file=out / "e.mkv",
    )
    assert outd["tv_season_folder_deleted"] is False
    assert "watched folder root" in (outd.get("tv_season_folder_skip_reason") or "").lower()


def test_tv_cleanup_blocked_output_too_small_for_prior_pass(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _, session = _sqlite_session(tmp_path)
    home = tmp_path / "h"
    home.mkdir()
    watched = tmp_path / "tvw"
    watched.mkdir()
    out = tmp_path / "out"
    out.mkdir()
    sdir = watched / "Serie" / "S01"
    sdir.mkdir(parents=True)
    ep = sdir / "e.mkv"
    ep.write_bytes(b"x" * 10_000)
    other = sdir / "o.mkv"
    other.write_bytes(b"a" * 10_000)
    (out / "Serie" / "S01").mkdir(parents=True)
    (out / "Serie" / "S01" / "e.mkv").write_bytes(b"y" * 5000)
    (out / "Serie" / "S01" / "o.mkv").write_bytes(b"t")  # far below 1% of 10_000-byte source

    session.add(
        ActivityEvent(
            event_type=activity_c.REFINER_FILE_REMUX_PASS_COMPLETED,
            module="refiner",
            title="t",
            detail=json.dumps(
                {
                    "ok": True,
                    "dry_run": False,
                    "media_scope": "tv",
                    "relative_media_path": "Serie/S01/o.mkv",
                    "outcome": REMUX_PASS_OUTCOME_LIVE_SKIPPED_NOT_REQUIRED,
                },
            ),
        ),
    )
    session.commit()

    monkeypatch.setattr(
        "mediamop.modules.refiner.refiner_tv_season_folder_cleanup.fetch_radarr_and_sonarr_queue_rows_for_scan",
        lambda _s, _settings: ([], [], None, None),
    )

    settings = replace(MediaMopSettings.load(), mediamop_home=str(home), refiner_watched_folder_min_file_age_seconds=0)
    rt = _tv_runtime(watched=watched, out=out, home=home)
    outd: dict = {}
    handle_tv_cleanup_after_success(
        session=session,
        settings=settings,
        path_runtime=rt,
        src=ep,
        watched_root=watched,
        out=outd,
        dry_run=False,
        min_file_age_seconds=0,
        current_job_id=1,
        remux_context={
            "ok": True,
            "dry_run": False,
            "outcome": REMUX_PASS_OUTCOME_LIVE_SKIPPED_NOT_REQUIRED,
            "relative_media_path": "Serie/S01/e.mkv",
        },
        final_output_file=out / "Serie" / "S01" / "e.mkv",
    )
    assert outd["tv_season_folder_deleted"] is False
    assert sdir.exists()


def test_tv_cleanup_blocked_when_sonarr_queue_holds_sibling_episode(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _, session = _sqlite_session(tmp_path)
    home = tmp_path / "h"
    home.mkdir()
    watched = tmp_path / "tvw"
    watched.mkdir()
    out = tmp_path / "out"
    out.mkdir()
    sdir = watched / "Serie" / "S01"
    sdir.mkdir(parents=True)
    ep = sdir / "e.mkv"
    ep.write_bytes(b"x" * 500)
    queued = sdir / "queued.mkv"
    queued.write_bytes(b"q" * 500)
    (out / "Serie" / "S01").mkdir(parents=True)
    (out / "Serie" / "S01" / "e.mkv").write_bytes(b"y" * 100)
    (out / "Serie" / "S01" / "queued.mkv").write_bytes(b"z" * 100)

    def _fetch(_s, _settings):
        son = [{"outputPath": str(queued.resolve()), "status": "importpending"}]
        return [], son, None, None

    monkeypatch.setattr(
        "mediamop.modules.refiner.refiner_tv_season_folder_cleanup.fetch_radarr_and_sonarr_queue_rows_for_scan",
        _fetch,
    )

    settings = replace(MediaMopSettings.load(), mediamop_home=str(home), refiner_watched_folder_min_file_age_seconds=0)
    rt = _tv_runtime(watched=watched, out=out, home=home)
    outd: dict = {}
    handle_tv_cleanup_after_success(
        session=session,
        settings=settings,
        path_runtime=rt,
        src=ep,
        watched_root=watched,
        out=outd,
        dry_run=False,
        min_file_age_seconds=0,
        current_job_id=1,
        remux_context={
            "ok": True,
            "dry_run": False,
            "outcome": REMUX_PASS_OUTCOME_LIVE_SKIPPED_NOT_REQUIRED,
            "relative_media_path": "Serie/S01/e.mkv",
        },
        final_output_file=out / "Serie" / "S01" / "e.mkv",
    )
    assert outd["tv_season_folder_deleted"] is False
    assert "Sonarr" in (outd.get("tv_season_folder_skip_reason") or "")
    assert sdir.exists()


def test_tv_cleanup_check4_never_processed_old_sibling_passes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _, session = _sqlite_session(tmp_path)
    home = tmp_path / "h"
    home.mkdir()
    watched = tmp_path / "tvw"
    watched.mkdir()
    out = tmp_path / "out"
    out.mkdir()
    sdir = watched / "Serie" / "S01"
    sdir.mkdir(parents=True)
    ep = sdir / "e.mkv"
    ep.write_bytes(b"x" * 500)
    other = sdir / "old.mkv"
    other.write_bytes(b"o" * 400)
    old = time.time() - 500_000
    os.utime(other, (old, old))
    (out / "Serie" / "S01").mkdir(parents=True)
    (out / "Serie" / "S01" / "e.mkv").write_bytes(b"y" * 100)

    monkeypatch.setattr(
        "mediamop.modules.refiner.refiner_tv_season_folder_cleanup.fetch_radarr_and_sonarr_queue_rows_for_scan",
        lambda _s, _settings: ([], [], None, None),
    )

    settings = replace(MediaMopSettings.load(), mediamop_home=str(home), refiner_watched_folder_min_file_age_seconds=0)
    rt = _tv_runtime(watched=watched, out=out, home=home)
    outd: dict = {}
    handle_tv_cleanup_after_success(
        session=session,
        settings=settings,
        path_runtime=rt,
        src=ep,
        watched_root=watched,
        out=outd,
        dry_run=False,
        min_file_age_seconds=60,
        current_job_id=1,
        remux_context={
            "ok": True,
            "dry_run": False,
            "outcome": REMUX_PASS_OUTCOME_LIVE_SKIPPED_NOT_REQUIRED,
            "relative_media_path": "Serie/S01/e.mkv",
        },
        final_output_file=out / "Serie" / "S01" / "e.mkv",
    )
    assert outd["tv_season_folder_deleted"] is True
    assert not sdir.exists()


def test_tv_cleanup_check4_blocked_when_min_age_not_met(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _, session = _sqlite_session(tmp_path)
    home = tmp_path / "h"
    home.mkdir()
    watched = tmp_path / "tvw"
    watched.mkdir()
    out = tmp_path / "out"
    out.mkdir()
    sdir = watched / "Serie" / "S01"
    sdir.mkdir(parents=True)
    ep = sdir / "e.mkv"
    ep.write_bytes(b"x" * 500)
    other = sdir / "new.mkv"
    other.write_bytes(b"n" * 400)
    (out / "Serie" / "S01").mkdir(parents=True)
    (out / "Serie" / "S01" / "e.mkv").write_bytes(b"y" * 100)

    monkeypatch.setattr(
        "mediamop.modules.refiner.refiner_tv_season_folder_cleanup.fetch_radarr_and_sonarr_queue_rows_for_scan",
        lambda _s, _settings: ([], [], None, None),
    )

    settings = replace(MediaMopSettings.load(), mediamop_home=str(home), refiner_watched_folder_min_file_age_seconds=0)
    rt = _tv_runtime(watched=watched, out=out, home=home)
    outd: dict = {}
    handle_tv_cleanup_after_success(
        session=session,
        settings=settings,
        path_runtime=rt,
        src=ep,
        watched_root=watched,
        out=outd,
        dry_run=False,
        min_file_age_seconds=86_400,
        current_job_id=1,
        remux_context={
            "ok": True,
            "dry_run": False,
            "outcome": REMUX_PASS_OUTCOME_LIVE_SKIPPED_NOT_REQUIRED,
            "relative_media_path": "Serie/S01/e.mkv",
        },
        final_output_file=out / "Serie" / "S01" / "e.mkv",
    )
    assert outd["tv_season_folder_deleted"] is False
    skip = (outd.get("tv_season_folder_skip_reason") or "").lower()
    assert "minimum" in skip or "age" in skip
    assert sdir.exists()


def test_tv_cleanup_activity_movie_scope_ignored_for_prior_success(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _, session = _sqlite_session(tmp_path)
    home = tmp_path / "h"
    home.mkdir()
    watched = tmp_path / "tvw"
    watched.mkdir()
    out = tmp_path / "out"
    out.mkdir()
    sdir = watched / "Serie" / "S01"
    sdir.mkdir(parents=True)
    ep = sdir / "e.mkv"
    ep.write_bytes(b"x" * 500)
    other = sdir / "o.mkv"
    other.write_bytes(b"o" * 500)
    (out / "Serie" / "S01").mkdir(parents=True)
    (out / "Serie" / "S01" / "e.mkv").write_bytes(b"y" * 100)

    session.add(
        ActivityEvent(
            event_type=activity_c.REFINER_FILE_REMUX_PASS_COMPLETED,
            module="refiner",
            title="t",
            detail=json.dumps(
                {
                    "ok": True,
                    "dry_run": False,
                    "media_scope": "movie",
                    "relative_media_path": "Serie/S01/o.mkv",
                    "outcome": REMUX_PASS_OUTCOME_LIVE_SKIPPED_NOT_REQUIRED,
                },
            ),
        ),
    )
    session.commit()

    monkeypatch.setattr(
        "mediamop.modules.refiner.refiner_tv_season_folder_cleanup.fetch_radarr_and_sonarr_queue_rows_for_scan",
        lambda _s, _settings: ([], [], None, None),
    )

    settings = replace(MediaMopSettings.load(), mediamop_home=str(home), refiner_watched_folder_min_file_age_seconds=0)
    rt = _tv_runtime(watched=watched, out=out, home=home)
    outd: dict = {}
    handle_tv_cleanup_after_success(
        session=session,
        settings=settings,
        path_runtime=rt,
        src=ep,
        watched_root=watched,
        out=outd,
        dry_run=False,
        min_file_age_seconds=86_400,
        current_job_id=1,
        remux_context={
            "ok": True,
            "dry_run": False,
            "outcome": REMUX_PASS_OUTCOME_LIVE_SKIPPED_NOT_REQUIRED,
            "relative_media_path": "Serie/S01/e.mkv",
        },
        final_output_file=out / "Serie" / "S01" / "e.mkv",
    )
    assert outd["tv_season_folder_deleted"] is False
    assert sdir.exists()


def test_tv_cleanup_failed_tv_activity_does_not_clear_episode(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _, session = _sqlite_session(tmp_path)
    home = tmp_path / "h"
    home.mkdir()
    watched = tmp_path / "tvw"
    watched.mkdir()
    out = tmp_path / "out"
    out.mkdir()
    sdir = watched / "Serie" / "S01"
    sdir.mkdir(parents=True)
    ep = sdir / "e.mkv"
    ep.write_bytes(b"x" * 500)
    other = sdir / "o.mkv"
    other.write_bytes(b"o" * 500)
    (out / "Serie" / "S01").mkdir(parents=True)
    (out / "Serie" / "S01" / "e.mkv").write_bytes(b"y" * 100)

    session.add(
        ActivityEvent(
            event_type=activity_c.REFINER_FILE_REMUX_PASS_COMPLETED,
            module="refiner",
            title="t",
            detail=json.dumps(
                {
                    "ok": False,
                    "dry_run": False,
                    "media_scope": "tv",
                    "relative_media_path": "Serie/S01/o.mkv",
                    "outcome": REMUX_PASS_OUTCOME_LIVE_OUTPUT_WRITTEN,
                },
            ),
        ),
    )
    session.commit()

    monkeypatch.setattr(
        "mediamop.modules.refiner.refiner_tv_season_folder_cleanup.fetch_radarr_and_sonarr_queue_rows_for_scan",
        lambda _s, _settings: ([], [], None, None),
    )

    settings = replace(MediaMopSettings.load(), mediamop_home=str(home), refiner_watched_folder_min_file_age_seconds=0)
    rt = _tv_runtime(watched=watched, out=out, home=home)
    outd: dict = {}
    handle_tv_cleanup_after_success(
        session=session,
        settings=settings,
        path_runtime=rt,
        src=ep,
        watched_root=watched,
        out=outd,
        dry_run=False,
        min_file_age_seconds=86_400,
        current_job_id=1,
        remux_context={
            "ok": True,
            "dry_run": False,
            "outcome": REMUX_PASS_OUTCOME_LIVE_SKIPPED_NOT_REQUIRED,
            "relative_media_path": "Serie/S01/e.mkv",
        },
        final_output_file=out / "Serie" / "S01" / "e.mkv",
    )
    assert outd["tv_season_folder_deleted"] is False
    assert sdir.exists()


def test_tv_cleanup_dry_run_activity_row_does_not_count_as_tv_success(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _, session = _sqlite_session(tmp_path)
    home = tmp_path / "h"
    home.mkdir()
    watched = tmp_path / "tvw"
    watched.mkdir()
    out = tmp_path / "out"
    out.mkdir()
    sdir = watched / "Serie" / "S01"
    sdir.mkdir(parents=True)
    ep = sdir / "e.mkv"
    ep.write_bytes(b"x" * 500)
    other = sdir / "o.mkv"
    other.write_bytes(b"o" * 500)
    (out / "Serie" / "S01").mkdir(parents=True)
    (out / "Serie" / "S01" / "e.mkv").write_bytes(b"y" * 100)
    (out / "Serie" / "S01" / "o.mkv").write_bytes(b"z" * 100)

    session.add(
        ActivityEvent(
            event_type=activity_c.REFINER_FILE_REMUX_PASS_COMPLETED,
            module="refiner",
            title="t",
            detail=json.dumps(
                {
                    "ok": True,
                    "dry_run": True,
                    "media_scope": "tv",
                    "relative_media_path": "Serie/S01/o.mkv",
                    "outcome": REMUX_PASS_OUTCOME_LIVE_SKIPPED_NOT_REQUIRED,
                },
            ),
        ),
    )
    session.commit()

    monkeypatch.setattr(
        "mediamop.modules.refiner.refiner_tv_season_folder_cleanup.fetch_radarr_and_sonarr_queue_rows_for_scan",
        lambda _s, _settings: ([], [], None, None),
    )

    settings = replace(MediaMopSettings.load(), mediamop_home=str(home), refiner_watched_folder_min_file_age_seconds=0)
    rt = _tv_runtime(watched=watched, out=out, home=home)
    outd: dict = {}
    handle_tv_cleanup_after_success(
        session=session,
        settings=settings,
        path_runtime=rt,
        src=ep,
        watched_root=watched,
        out=outd,
        dry_run=False,
        min_file_age_seconds=86_400,
        current_job_id=1,
        remux_context={
            "ok": True,
            "dry_run": False,
            "outcome": REMUX_PASS_OUTCOME_LIVE_SKIPPED_NOT_REQUIRED,
            "relative_media_path": "Serie/S01/e.mkv",
        },
        final_output_file=out / "Serie" / "S01" / "e.mkv",
    )
    assert outd["tv_season_folder_deleted"] is False
    assert sdir.exists()


def test_tv_cleanup_blocked_when_prior_tv_success_but_output_missing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _, session = _sqlite_session(tmp_path)
    home = tmp_path / "h"
    home.mkdir()
    watched = tmp_path / "tvw"
    watched.mkdir()
    out = tmp_path / "out"
    out.mkdir()
    sdir = watched / "Serie" / "S01"
    sdir.mkdir(parents=True)
    ep = sdir / "e.mkv"
    ep.write_bytes(b"x" * 500)
    other = sdir / "o.mkv"
    other.write_bytes(b"o" * 500)
    (out / "Serie" / "S01").mkdir(parents=True)
    (out / "Serie" / "S01" / "e.mkv").write_bytes(b"y" * 100)

    session.add(
        ActivityEvent(
            event_type=activity_c.REFINER_FILE_REMUX_PASS_COMPLETED,
            module="refiner",
            title="t",
            detail=json.dumps(
                {
                    "ok": True,
                    "dry_run": False,
                    "media_scope": "tv",
                    "relative_media_path": "Serie/S01/o.mkv",
                    "outcome": REMUX_PASS_OUTCOME_LIVE_SKIPPED_NOT_REQUIRED,
                },
            ),
        ),
    )
    session.commit()

    monkeypatch.setattr(
        "mediamop.modules.refiner.refiner_tv_season_folder_cleanup.fetch_radarr_and_sonarr_queue_rows_for_scan",
        lambda _s, _settings: ([], [], None, None),
    )

    settings = replace(MediaMopSettings.load(), mediamop_home=str(home), refiner_watched_folder_min_file_age_seconds=0)
    rt = _tv_runtime(watched=watched, out=out, home=home)
    outd: dict = {}
    handle_tv_cleanup_after_success(
        session=session,
        settings=settings,
        path_runtime=rt,
        src=ep,
        watched_root=watched,
        out=outd,
        dry_run=False,
        min_file_age_seconds=0,
        current_job_id=1,
        remux_context={
            "ok": True,
            "dry_run": False,
            "outcome": REMUX_PASS_OUTCOME_LIVE_SKIPPED_NOT_REQUIRED,
            "relative_media_path": "Serie/S01/e.mkv",
        },
        final_output_file=out / "Serie" / "S01" / "e.mkv",
    )
    assert outd["tv_season_folder_deleted"] is False
    assert "missing" in (outd.get("tv_season_folder_skip_reason") or "").lower()
    assert sdir.exists()


def test_tv_cleanup_rmtree_oserror_skips_season(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _, session = _sqlite_session(tmp_path)
    home = tmp_path / "h"
    home.mkdir()
    watched = tmp_path / "tvw"
    watched.mkdir()
    out = tmp_path / "out"
    out.mkdir()
    sdir = watched / "Serie" / "S01"
    sdir.mkdir(parents=True)
    ep = sdir / "e.mkv"
    ep.write_bytes(b"x" * 500)
    (out / "Serie" / "S01").mkdir(parents=True)
    (out / "Serie" / "S01" / "e.mkv").write_bytes(b"y" * 100)

    monkeypatch.setattr(
        "mediamop.modules.refiner.refiner_tv_season_folder_cleanup.fetch_radarr_and_sonarr_queue_rows_for_scan",
        lambda _s, _settings: ([], [], None, None),
    )

    def _boom(_path, ignore_errors=False, onerror=None):
        raise OSError("locked")

    monkeypatch.setattr("mediamop.modules.refiner.refiner_tv_season_folder_cleanup.shutil.rmtree", _boom)

    settings = replace(MediaMopSettings.load(), mediamop_home=str(home), refiner_watched_folder_min_file_age_seconds=0)
    rt = _tv_runtime(watched=watched, out=out, home=home)
    outd: dict = {}
    handle_tv_cleanup_after_success(
        session=session,
        settings=settings,
        path_runtime=rt,
        src=ep,
        watched_root=watched,
        out=outd,
        dry_run=False,
        min_file_age_seconds=0,
        current_job_id=1,
        remux_context={
            "ok": True,
            "dry_run": False,
            "outcome": REMUX_PASS_OUTCOME_LIVE_SKIPPED_NOT_REQUIRED,
            "relative_media_path": "Serie/S01/e.mkv",
        },
        final_output_file=out / "Serie" / "S01" / "e.mkv",
    )
    assert outd["tv_season_folder_deleted"] is False
    assert "in use or locked" in (outd.get("tv_season_folder_skip_reason") or "").lower()
    assert sdir.exists()


def test_tv_cleanup_cascade_removes_empty_show_folder(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _, session = _sqlite_session(tmp_path)
    home = tmp_path / "h"
    home.mkdir()
    watched = tmp_path / "tvw"
    watched.mkdir()
    out = tmp_path / "out"
    out.mkdir()
    show = watched / "Serie"
    show.mkdir()
    sdir = show / "S01"
    sdir.mkdir()
    ep = sdir / "e.mkv"
    ep.write_bytes(b"x" * 500)
    (out / "Serie" / "S01").mkdir(parents=True)
    (out / "Serie" / "S01" / "e.mkv").write_bytes(b"y" * 100)

    monkeypatch.setattr(
        "mediamop.modules.refiner.refiner_tv_season_folder_cleanup.fetch_radarr_and_sonarr_queue_rows_for_scan",
        lambda _s, _settings: ([], [], None, None),
    )

    settings = replace(MediaMopSettings.load(), mediamop_home=str(home), refiner_watched_folder_min_file_age_seconds=0)
    rt = _tv_runtime(watched=watched, out=out, home=home)
    outd: dict = {}
    handle_tv_cleanup_after_success(
        session=session,
        settings=settings,
        path_runtime=rt,
        src=ep,
        watched_root=watched,
        out=outd,
        dry_run=False,
        min_file_age_seconds=0,
        current_job_id=1,
        remux_context={
            "ok": True,
            "dry_run": False,
            "outcome": REMUX_PASS_OUTCOME_LIVE_SKIPPED_NOT_REQUIRED,
            "relative_media_path": "Serie/S01/e.mkv",
        },
        final_output_file=out / "Serie" / "S01" / "e.mkv",
    )
    assert outd["tv_season_folder_deleted"] is True
    assert not sdir.exists()
    assert not show.exists()
    assert watched.is_dir()
    cascade = outd.get("tv_cascade_folders_deleted") or []
    assert any("Serie" in str(p) for p in cascade)
