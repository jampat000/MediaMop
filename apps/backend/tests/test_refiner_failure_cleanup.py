"""Tests for Refiner Pass 4 terminal failed remux cleanup sweep."""

from __future__ import annotations

import json
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

import mediamop.modules.refiner.jobs_model  # noqa: F401
from mediamop.core.config import MediaMopSettings
from mediamop.core.db import Base
from mediamop.modules.refiner.jobs_model import RefinerJob, RefinerJobStatus
from mediamop.modules.refiner.refiner_failure_cleanup import run_refiner_failure_cleanup_sweep_for_scope
from mediamop.modules.refiner.refiner_file_remux_pass_job_kinds import REFINER_FILE_REMUX_PASS_JOB_KIND
from mediamop.modules.refiner.refiner_path_settings_model import RefinerPathSettingsRow


def _session(tmp_path: Path) -> Session:
    engine = create_engine(f"sqlite:///{tmp_path / 't.sqlite'}", connect_args={"check_same_thread": False}, future=True)
    Base.metadata.create_all(engine)
    fac = sessionmaker(bind=engine, class_=Session, autoflush=False, autocommit=False, future=True)
    return fac()


def _settings() -> MediaMopSettings:
    return replace(MediaMopSettings.load())


def _seed_paths(session: Session, *, mw: Path, mo: Path, tw: Path, to: Path) -> None:
    session.add(
        RefinerPathSettingsRow(
            id=1,
            refiner_watched_folder=str(mw.resolve()),
            refiner_output_folder=str(mo.resolve()),
            refiner_tv_watched_folder=str(tw.resolve()),
            refiner_tv_output_folder=str(to.resolve()),
            refiner_work_folder=str((mw.parent / "mwork").resolve()),
            refiner_tv_work_folder=str((tw.parent / "twork").resolve()),
        ),
    )
    session.commit()


def _add_failed(session: Session, *, rel: str, scope: str, dry_run: bool = False) -> RefinerJob:
    row = RefinerJob(
        dedupe_key=f"x:{scope}:{rel}",
        job_kind=REFINER_FILE_REMUX_PASS_JOB_KIND,
        status=RefinerJobStatus.FAILED.value,
        payload_json=json.dumps({"relative_media_path": rel, "media_scope": scope, "dry_run": dry_run}, separators=(",", ":")),
    )
    session.add(row)
    session.flush()
    row.updated_at = datetime.now(UTC) - timedelta(hours=1)
    session.commit()
    return row


def _add_pending(session: Session, *, rel: str, scope: str) -> RefinerJob:
    row = RefinerJob(
        dedupe_key=f"p:{scope}:{rel}",
        job_kind=REFINER_FILE_REMUX_PASS_JOB_KIND,
        status=RefinerJobStatus.PENDING.value,
        payload_json=json.dumps({"relative_media_path": rel, "media_scope": scope}, separators=(",", ":")),
    )
    session.add(row)
    session.commit()
    return row


def test_failed_movie_older_than_grace_cleans_source_output_and_temp(tmp_path: Path) -> None:
    session = _session(tmp_path)
    mw = tmp_path / "mw"
    mo = tmp_path / "mo"
    tw = tmp_path / "tw"
    to = tmp_path / "to"
    for p in (mw, mo, tw, to, tmp_path / "mwork", tmp_path / "twork"):
        p.mkdir(parents=True, exist_ok=True)
    rel = "Title/Film.mkv"
    src = mw / rel
    out = mo / rel
    src.parent.mkdir(parents=True, exist_ok=True)
    out.parent.mkdir(parents=True, exist_ok=True)
    src.write_bytes(b"a")
    out.write_bytes(b"b")
    temp = (tmp_path / "mwork" / "Film.refiner.tmp.mkv")
    temp.write_bytes(b"c")
    _seed_paths(session, mw=mw, mo=mo, tw=tw, to=to)
    _add_failed(session, rel=rel, scope="movie")
    settings = replace(_settings(), refiner_movie_failure_cleanup_grace_period_seconds=300)
    with (
        patch(
            "mediamop.modules.refiner.refiner_failure_cleanup.resolve_radarr_http_credentials",
            return_value=("http://radarr.local", "abc"),
        ),
        patch("mediamop.modules.refiner.refiner_failure_cleanup.fetch_arr_v3_queue_rows", return_value=[]),
    ):
        result = run_refiner_failure_cleanup_sweep_for_scope(session=session, settings=settings, media_scope="movie")
    job = result["jobs"][0]
    assert job["movie_failure_cleanup_ran"] is True
    assert job["movie_failure_cleanup_queue_check"] == "passed_not_in_queue"
    assert job["movie_failure_cleanup_source_folder_deleted"] is True
    assert job["movie_failure_cleanup_output_folder_deleted"] is True
    assert str(temp.resolve()) in job["movie_failure_cleanup_temp_files_deleted"]


def test_failed_movie_in_radarr_queue_skips(tmp_path: Path) -> None:
    session = _session(tmp_path)
    mw = tmp_path / "mw"
    mo = tmp_path / "mo"
    tw = tmp_path / "tw"
    to = tmp_path / "to"
    for p in (mw, mo, tw, to, tmp_path / "mwork", tmp_path / "twork"):
        p.mkdir(parents=True, exist_ok=True)
    rel = "Title/Film.mkv"
    src = mw / rel
    src.parent.mkdir(parents=True, exist_ok=True)
    src.write_bytes(b"a")
    _seed_paths(session, mw=mw, mo=mo, tw=tw, to=to)
    _add_failed(session, rel=rel, scope="movie")
    settings = replace(_settings(), refiner_movie_failure_cleanup_grace_period_seconds=300)
    with (
        patch(
            "mediamop.modules.refiner.refiner_failure_cleanup.resolve_radarr_http_credentials",
            return_value=("http://radarr.local", "abc"),
        ),
        patch(
            "mediamop.modules.refiner.refiner_failure_cleanup.fetch_arr_v3_queue_rows",
            return_value=[{"outputPath": str(src.resolve())}],
        ),
    ):
        result = run_refiner_failure_cleanup_sweep_for_scope(session=session, settings=settings, media_scope="movie")
    job = result["jobs"][0]
    assert job["movie_failure_cleanup_ran"] is False
    assert job["movie_failure_cleanup_queue_check"] == "blocked_in_queue"


def test_failed_movie_dry_run_job_skips_entirely(tmp_path: Path) -> None:
    session = _session(tmp_path)
    root = tmp_path
    for p in ("mw", "mo", "tw", "to", "mwork", "twork"):
        (root / p).mkdir(parents=True, exist_ok=True)
    _seed_paths(session, mw=root / "mw", mo=root / "mo", tw=root / "tw", to=root / "to")
    _add_failed(session, rel="Title/Film.mkv", scope="movie", dry_run=True)
    result = run_refiner_failure_cleanup_sweep_for_scope(session=session, settings=_settings(), media_scope="movie")
    job = result["jobs"][0]
    assert job["movie_failure_cleanup_dry_run"] is True
    assert "compatibility" in job["movie_failure_cleanup_skip_reason"]


def test_tv_cleanup_skips_when_any_direct_child_episode_still_in_queue(tmp_path: Path) -> None:
    session = _session(tmp_path)
    mw = tmp_path / "mw"
    mo = tmp_path / "mo"
    tw = tmp_path / "tw"
    to = tmp_path / "to"
    for p in (mw, mo, tw, to, tmp_path / "mwork", tmp_path / "twork"):
        p.mkdir(parents=True, exist_ok=True)
    rel = "Show/Season 1/S01E01.mkv"
    ep1 = tw / "Show/Season 1/S01E01.mkv"
    ep2 = tw / "Show/Season 1/S01E02.mkv"
    ep1.parent.mkdir(parents=True, exist_ok=True)
    ep1.write_bytes(b"1")
    ep2.write_bytes(b"2")
    _seed_paths(session, mw=mw, mo=mo, tw=tw, to=to)
    _add_failed(session, rel=rel, scope="tv")
    with (
        patch(
            "mediamop.modules.refiner.refiner_failure_cleanup.resolve_sonarr_http_credentials",
            return_value=("http://sonarr.local", "abc"),
        ),
        patch(
            "mediamop.modules.refiner.refiner_failure_cleanup.fetch_arr_v3_queue_rows",
            return_value=[{"outputPath": str(ep2.resolve())}],
        ),
    ):
        result = run_refiner_failure_cleanup_sweep_for_scope(session=session, settings=_settings(), media_scope="tv")
    job = result["jobs"][0]
    assert job["tv_failure_cleanup_ran"] is False
    assert job["tv_failure_cleanup_queue_check"] == "blocked_in_queue_or_active_job"


def test_missing_path_settings_skip_cleanly(tmp_path: Path) -> None:
    session = _session(tmp_path)
    session.add(RefinerPathSettingsRow(id=1, refiner_watched_folder=None, refiner_output_folder=""))
    session.commit()
    result = run_refiner_failure_cleanup_sweep_for_scope(session=session, settings=_settings(), media_scope="movie")
    assert "not configured" in result["skip_reason"]


def test_failed_movie_radarr_unreachable_skips(tmp_path: Path) -> None:
    session = _session(tmp_path)
    root = tmp_path
    for p in ("mw", "mo", "tw", "to", "mwork", "twork"):
        (root / p).mkdir(parents=True, exist_ok=True)
    _seed_paths(session, mw=root / "mw", mo=root / "mo", tw=root / "tw", to=root / "to")
    _add_failed(session, rel="Title/Film.mkv", scope="movie")
    with patch(
        "mediamop.modules.refiner.refiner_failure_cleanup.resolve_radarr_http_credentials",
        return_value=(None, None),
    ):
        result = run_refiner_failure_cleanup_sweep_for_scope(session=session, settings=_settings(), media_scope="movie")
    job = result["jobs"][0]
    assert job["movie_failure_cleanup_ran"] is False
    assert "ARR queue check was unavailable" in job["movie_failure_cleanup_skip_reason"]


def test_failed_movie_root_bounds_prevent_root_delete(tmp_path: Path) -> None:
    session = _session(tmp_path)
    root = tmp_path
    for p in ("mw", "mo", "tw", "to", "mwork", "twork"):
        (root / p).mkdir(parents=True, exist_ok=True)
    # relative path directly at watched root: source parent is root and must not be deleted.
    (root / "mw" / "Film.mkv").write_bytes(b"x")
    (root / "mo" / "Film.mkv").write_bytes(b"y")
    _seed_paths(session, mw=root / "mw", mo=root / "mo", tw=root / "tw", to=root / "to")
    _add_failed(session, rel="Film.mkv", scope="movie")
    with (
        patch(
            "mediamop.modules.refiner.refiner_failure_cleanup.resolve_radarr_http_credentials",
            return_value=("http://radarr.local", "abc"),
        ),
        patch("mediamop.modules.refiner.refiner_failure_cleanup.fetch_arr_v3_queue_rows", return_value=[]),
    ):
        result = run_refiner_failure_cleanup_sweep_for_scope(session=session, settings=_settings(), media_scope="movie")
    job = result["jobs"][0]
    assert job["movie_failure_cleanup_source_folder_deleted"] is False
    assert Path(job["movie_failure_cleanup_source_folder_path"]).resolve() == (root / "mw").resolve()


def test_tv_pending_or_leased_job_blocks_season_delete(tmp_path: Path) -> None:
    session = _session(tmp_path)
    root = tmp_path
    for p in ("mw", "mo", "tw", "to", "mwork", "twork"):
        (root / p).mkdir(parents=True, exist_ok=True)
    ep1 = root / "tw/Show/Season 1/S01E01.mkv"
    ep2 = root / "tw/Show/Season 1/S01E02.mkv"
    ep1.parent.mkdir(parents=True, exist_ok=True)
    ep1.write_bytes(b"1")
    ep2.write_bytes(b"2")
    _seed_paths(session, mw=root / "mw", mo=root / "mo", tw=root / "tw", to=root / "to")
    _add_failed(session, rel="Show/Season 1/S01E01.mkv", scope="tv")
    _add_failed(session, rel="Show/Season 1/S01E02.mkv", scope="tv")
    _add_pending(session, rel="Show/Season 1/S01E02.mkv", scope="tv")
    with (
        patch(
            "mediamop.modules.refiner.refiner_failure_cleanup.resolve_sonarr_http_credentials",
            return_value=("http://sonarr.local", "abc"),
        ),
        patch("mediamop.modules.refiner.refiner_failure_cleanup.fetch_arr_v3_queue_rows", return_value=[]),
    ):
        result = run_refiner_failure_cleanup_sweep_for_scope(session=session, settings=_settings(), media_scope="tv")
    job = result["jobs"][0]
    assert job["tv_failure_cleanup_ran"] is False
    assert job["tv_failure_cleanup_queue_check"] == "blocked_in_queue_or_active_job"


def test_tv_season_delete_requires_terminal_failed_for_every_direct_child_episode(tmp_path: Path) -> None:
    session = _session(tmp_path)
    root = tmp_path
    for p in ("mw", "mo", "tw", "to", "mwork", "twork"):
        (root / p).mkdir(parents=True, exist_ok=True)
    ep1 = root / "tw/Show/Season 1/S01E01.mkv"
    ep2 = root / "tw/Show/Season 1/S01E02.mkv"
    ep1.parent.mkdir(parents=True, exist_ok=True)
    ep1.write_bytes(b"1")
    ep2.write_bytes(b"2")
    _seed_paths(session, mw=root / "mw", mo=root / "mo", tw=root / "tw", to=root / "to")
    # Only one episode has terminal failed remux outcome.
    _add_failed(session, rel="Show/Season 1/S01E01.mkv", scope="tv")
    with (
        patch(
            "mediamop.modules.refiner.refiner_failure_cleanup.resolve_sonarr_http_credentials",
            return_value=("http://sonarr.local", "abc"),
        ),
        patch("mediamop.modules.refiner.refiner_failure_cleanup.fetch_arr_v3_queue_rows", return_value=[]),
    ):
        result = run_refiner_failure_cleanup_sweep_for_scope(session=session, settings=_settings(), media_scope="tv")
    job = result["jobs"][0]
    assert job["tv_failure_cleanup_ran"] is False
    assert "terminal failed TV remux outcome" in job["tv_failure_cleanup_skip_reason"]


def test_tv_failed_job_dry_run_skips_entirely(tmp_path: Path) -> None:
    session = _session(tmp_path)
    root = tmp_path
    for p in ("mw", "mo", "tw", "to", "mwork", "twork"):
        (root / p).mkdir(parents=True, exist_ok=True)
    _seed_paths(session, mw=root / "mw", mo=root / "mo", tw=root / "tw", to=root / "to")
    _add_failed(session, rel="Show/Season 1/S01E01.mkv", scope="tv", dry_run=True)
    result = run_refiner_failure_cleanup_sweep_for_scope(session=session, settings=_settings(), media_scope="tv")
    job = result["jobs"][0]
    assert job["tv_failure_cleanup_dry_run"] is True
    assert "compatibility" in job["tv_failure_cleanup_skip_reason"]


def test_movies_scope_does_not_process_tv_failed_rows(tmp_path: Path) -> None:
    session = _session(tmp_path)
    root = tmp_path
    for p in ("mw", "mo", "tw", "to", "mwork", "twork"):
        (root / p).mkdir(parents=True, exist_ok=True)
    _seed_paths(session, mw=root / "mw", mo=root / "mo", tw=root / "tw", to=root / "to")
    _add_failed(session, rel="Show/Season 1/S01E01.mkv", scope="tv")
    with (
        patch(
            "mediamop.modules.refiner.refiner_failure_cleanup.resolve_radarr_http_credentials",
            return_value=("http://radarr.local", "abc"),
        ),
        patch("mediamop.modules.refiner.refiner_failure_cleanup.fetch_arr_v3_queue_rows", return_value=[]),
    ):
        result = run_refiner_failure_cleanup_sweep_for_scope(session=session, settings=_settings(), media_scope="movie")
    assert result["eligible_failed_jobs"] == 0


def test_tv_scope_does_not_process_movie_failed_rows(tmp_path: Path) -> None:
    session = _session(tmp_path)
    root = tmp_path
    for p in ("mw", "mo", "tw", "to", "mwork", "twork"):
        (root / p).mkdir(parents=True, exist_ok=True)
    _seed_paths(session, mw=root / "mw", mo=root / "mo", tw=root / "tw", to=root / "to")
    _add_failed(session, rel="Title/Film.mkv", scope="movie")
    with (
        patch(
            "mediamop.modules.refiner.refiner_failure_cleanup.resolve_sonarr_http_credentials",
            return_value=("http://sonarr.local", "abc"),
        ),
        patch("mediamop.modules.refiner.refiner_failure_cleanup.fetch_arr_v3_queue_rows", return_value=[]),
    ):
        result = run_refiner_failure_cleanup_sweep_for_scope(session=session, settings=_settings(), media_scope="tv")
    assert result["eligible_failed_jobs"] == 0


def test_lock_failures_non_fatal(tmp_path: Path) -> None:
    session = _session(tmp_path)
    root = tmp_path
    for p in ("mw", "mo", "tw", "to", "mwork", "twork"):
        (root / p).mkdir(parents=True, exist_ok=True)
    rel = "Title/Film.mkv"
    src = root / "mw" / rel
    out = root / "mo" / rel
    src.parent.mkdir(parents=True, exist_ok=True)
    out.parent.mkdir(parents=True, exist_ok=True)
    src.write_bytes(b"a")
    out.write_bytes(b"b")
    _seed_paths(session, mw=root / "mw", mo=root / "mo", tw=root / "tw", to=root / "to")
    _add_failed(session, rel=rel, scope="movie")
    with (
        patch(
            "mediamop.modules.refiner.refiner_failure_cleanup.resolve_radarr_http_credentials",
            return_value=("http://radarr.local", "abc"),
        ),
        patch("mediamop.modules.refiner.refiner_failure_cleanup.fetch_arr_v3_queue_rows", return_value=[]),
        patch("mediamop.modules.refiner.refiner_failure_cleanup.shutil.rmtree", side_effect=PermissionError("locked")),
    ):
        result = run_refiner_failure_cleanup_sweep_for_scope(session=session, settings=_settings(), media_scope="movie")
    job = result["jobs"][0]
    assert job["movie_failure_cleanup_ran"] is True
    assert job["movie_failure_cleanup_source_folder_deleted"] is False


def test_per_scope_grace_settings_are_independent(tmp_path: Path) -> None:
    session = _session(tmp_path)
    root = tmp_path
    for p in ("mw", "mo", "tw", "to", "mwork", "twork"):
        (root / p).mkdir(parents=True, exist_ok=True)
    _seed_paths(session, mw=root / "mw", mo=root / "mo", tw=root / "tw", to=root / "to")
    m = _add_failed(session, rel="Title/Film.mkv", scope="movie")
    t = _add_failed(session, rel="Show/Season 1/S01E01.mkv", scope="tv")
    now = datetime.now(UTC)
    m.updated_at = now - timedelta(seconds=700)
    t.updated_at = now - timedelta(seconds=700)
    session.commit()
    settings = replace(
        _settings(),
        refiner_movie_failure_cleanup_grace_period_seconds=600,
        refiner_tv_failure_cleanup_grace_period_seconds=1200,
    )
    with (
        patch(
            "mediamop.modules.refiner.refiner_failure_cleanup.resolve_radarr_http_credentials",
            return_value=("http://radarr.local", "abc"),
        ),
        patch(
            "mediamop.modules.refiner.refiner_failure_cleanup.resolve_sonarr_http_credentials",
            return_value=("http://sonarr.local", "abc"),
        ),
        patch("mediamop.modules.refiner.refiner_failure_cleanup.fetch_arr_v3_queue_rows", return_value=[]),
    ):
        movie_res = run_refiner_failure_cleanup_sweep_for_scope(session=session, settings=settings, media_scope="movie")
        tv_res = run_refiner_failure_cleanup_sweep_for_scope(session=session, settings=settings, media_scope="tv")
    assert movie_res["eligible_failed_jobs"] == 1
    assert tv_res["eligible_failed_jobs"] == 0

