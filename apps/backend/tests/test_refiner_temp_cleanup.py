"""Tests for Refiner work/temp stale sweep (Pass 2) — per-scope Movies vs TV."""

from __future__ import annotations

import json
import os
import time
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from sqlalchemy import create_engine, delete, select
from sqlalchemy.orm import Session, sessionmaker

import mediamop.modules.refiner.jobs_model  # noqa: F401
import mediamop.modules.refiner.refiner_temp_cleanup as refiner_temp_cleanup
from mediamop.core.config import MediaMopSettings
from mediamop.core.db import Base
from mediamop.modules.refiner.jobs_model import RefinerJob, RefinerJobStatus
from mediamop.modules.refiner.refiner_file_remux_pass_job_kinds import REFINER_FILE_REMUX_PASS_JOB_KIND
from mediamop.modules.refiner.refiner_temp_cleanup import (
    is_refiner_owned_temp_work_file,
    refiner_file_remux_pass_job_active_for_scope,
    run_refiner_work_temp_stale_sweep_for_scope,
)
from mediamop.modules.refiner.refiner_work_temp_stale_sweep_enqueue import (
    enqueue_refiner_work_temp_stale_sweep_job,
)
from mediamop.modules.refiner.refiner_work_temp_stale_sweep_job_kinds import (
    REFINER_WORK_TEMP_STALE_SWEEP_DEDUPE_KEY_MOVIE,
    REFINER_WORK_TEMP_STALE_SWEEP_DEDUPE_KEY_TV,
)


def _session(tmp_path: Path) -> tuple[sessionmaker[Session], Session]:
    url = f"sqlite:///{tmp_path / 't.sqlite'}"
    engine = create_engine(url, connect_args={"check_same_thread": False}, future=True)
    Base.metadata.create_all(engine)
    fac = sessionmaker(bind=engine, class_=Session, autoflush=False, autocommit=False, future=True)
    return fac, fac()


def _settings(*, min_stale: int = 0) -> MediaMopSettings:
    return replace(MediaMopSettings.load(), refiner_work_temp_stale_sweep_min_stale_age_seconds=min_stale)


def _patch_roots(movie: Path, tv: Path):
    def _fake(*, session: Session, settings: MediaMopSettings) -> tuple[Path, Path]:
        return movie.resolve(), tv.resolve()

    return patch.object(refiner_temp_cleanup, "_resolved_movie_and_tv_work_roots", _fake)


def test_is_refiner_owned_detects_mkstemp_pattern_and_placeholder(tmp_path: Path) -> None:
    a = tmp_path / "Show.S01E01.refiner.abc123.mkv"
    a.write_bytes(b"x")
    assert is_refiner_owned_temp_work_file(a) is True
    b = tmp_path / "dry-run-ffmpeg-destination-placeholder.mkv"
    b.write_bytes(b"y")
    assert is_refiner_owned_temp_work_file(b) is True
    c = tmp_path / "normal.mkv"
    c.write_bytes(b"z")
    assert is_refiner_owned_temp_work_file(c) is False


def test_stale_refiner_temp_deleted_movie_scope_when_old_enough(tmp_path: Path) -> None:
    _, session = _session(tmp_path)
    w_m = tmp_path / "movie_work"
    w_t = tmp_path / "tv_work"
    w_m.mkdir()
    w_t.mkdir()
    stale = w_m / "ep.refiner.xyz.mkv"
    stale.write_bytes(b"a")
    old = time.time() - 100_000
    os.utime(stale, (old, old))
    settings = _settings(min_stale=60)
    with _patch_roots(w_m, w_t):
        out = run_refiner_work_temp_stale_sweep_for_scope(
            session=session,
            settings=settings,
            media_scope="movie",
            dry_run=False,
        )
    assert out["media_scope"] == "movie"
    assert out["temp_cleanup_ran"] is True
    assert out["temp_cleanup_shared_work_root_conflict"] is False
    assert out["temp_cleanup_candidates_found"] == 1
    assert str(stale.resolve()) in out["temp_cleanup_files_deleted"]
    assert not stale.exists()


def test_movie_sweep_does_not_touch_tv_work_folder(tmp_path: Path) -> None:
    _, session = _session(tmp_path)
    w_m = tmp_path / "movie_work"
    w_t = tmp_path / "tv_work"
    w_m.mkdir()
    w_t.mkdir()
    tv_stale = w_t / "tvonly.refiner.a.mkv"
    tv_stale.write_bytes(b"x")
    old = time.time() - 100_000
    os.utime(tv_stale, (old, old))
    settings = _settings(min_stale=60)
    with _patch_roots(w_m, w_t):
        out = run_refiner_work_temp_stale_sweep_for_scope(
            session=session,
            settings=settings,
            media_scope="movie",
            dry_run=False,
        )
    assert tv_stale.exists()
    assert out["temp_cleanup_candidates_found"] == 0
    assert out["temp_cleanup_root_paths"] == [str(w_m.resolve())]


def test_fresh_refiner_temp_not_deleted_per_scope(tmp_path: Path) -> None:
    _, session = _session(tmp_path)
    w_m = tmp_path / "m"
    w_t = tmp_path / "t"
    w_m.mkdir()
    w_t.mkdir()
    fresh = w_m / "ep.refiner.new.mkv"
    fresh.write_bytes(b"b")
    settings = _settings(min_stale=86_400)
    with _patch_roots(w_m, w_t):
        out = run_refiner_work_temp_stale_sweep_for_scope(
            session=session,
            settings=settings,
            media_scope="movie",
            dry_run=False,
        )
    assert fresh.exists()
    assert out["temp_cleanup_candidates_found"] == 1
    assert out["temp_cleanup_files_deleted"] == []
    assert any("not stale enough" in s for s in out["temp_cleanup_files_skipped"])


def test_non_refiner_file_in_work_root_not_deleted(tmp_path: Path) -> None:
    _, session = _session(tmp_path)
    w_m = tmp_path / "m"
    w_t = tmp_path / "t"
    w_m.mkdir()
    w_t.mkdir()
    other = w_m / "operator-notes.txt"
    other.write_text("keep")
    settings = _settings(min_stale=0)
    with _patch_roots(w_m, w_t):
        out = run_refiner_work_temp_stale_sweep_for_scope(
            session=session,
            settings=settings,
            media_scope="movie",
            dry_run=False,
        )
    assert other.exists()
    assert out["temp_cleanup_candidates_found"] == 0


def test_movie_remux_blocks_movie_sweep_only_tv_still_deletes(tmp_path: Path) -> None:
    _, session = _session(tmp_path)
    w_m = tmp_path / "m"
    w_t = tmp_path / "t"
    w_m.mkdir()
    w_t.mkdir()
    fm = w_m / "m.refiner.1.mkv"
    ft = w_t / "t.refiner.2.mkv"
    fm.write_bytes(b"1")
    ft.write_bytes(b"2")
    old = time.time() - 200_000
    os.utime(fm, (old, old))
    os.utime(ft, (old, old))
    session.add(
        RefinerJob(
            dedupe_key="remux-movie",
            job_kind=REFINER_FILE_REMUX_PASS_JOB_KIND,
            payload_json=json.dumps(
                {"relative_media_path": "a.mkv", "dry_run": False, "media_scope": "movie"},
            ),
            status=RefinerJobStatus.PENDING.value,
            max_attempts=3,
        ),
    )
    session.commit()
    settings = _settings(min_stale=0)
    with _patch_roots(w_m, w_t):
        out_m = run_refiner_work_temp_stale_sweep_for_scope(
            session=session,
            settings=settings,
            media_scope="movie",
            dry_run=False,
        )
        out_t = run_refiner_work_temp_stale_sweep_for_scope(
            session=session,
            settings=settings,
            media_scope="tv",
            dry_run=False,
        )
    assert out_m["temp_cleanup_ran"] is False
    assert out_m["temp_cleanup_skipped_reason"]
    assert fm.exists()
    assert out_t["temp_cleanup_ran"] is True
    assert not ft.exists()
    assert str(ft.resolve()) in out_t["temp_cleanup_files_deleted"]


def test_tv_remux_blocks_tv_sweep_only_movie_still_deletes(tmp_path: Path) -> None:
    _, session = _session(tmp_path)
    w_m = tmp_path / "m"
    w_t = tmp_path / "t"
    w_m.mkdir()
    w_t.mkdir()
    fm = w_m / "m.refiner.1.mkv"
    ft = w_t / "t.refiner.2.mkv"
    fm.write_bytes(b"1")
    ft.write_bytes(b"2")
    old = time.time() - 200_000
    os.utime(fm, (old, old))
    os.utime(ft, (old, old))
    session.add(
        RefinerJob(
            dedupe_key="remux-tv",
            job_kind=REFINER_FILE_REMUX_PASS_JOB_KIND,
            payload_json=json.dumps(
                {"relative_media_path": "s01e01.mkv", "dry_run": False, "media_scope": "tv"},
            ),
            status=RefinerJobStatus.PENDING.value,
            max_attempts=3,
        ),
    )
    session.commit()
    settings = _settings(min_stale=0)
    with _patch_roots(w_m, w_t):
        out_m = run_refiner_work_temp_stale_sweep_for_scope(
            session=session,
            settings=settings,
            media_scope="movie",
            dry_run=False,
        )
        out_t = run_refiner_work_temp_stale_sweep_for_scope(
            session=session,
            settings=settings,
            media_scope="tv",
            dry_run=False,
        )
    assert out_t["temp_cleanup_ran"] is False
    assert ft.exists()
    assert out_m["temp_cleanup_ran"] is True
    assert not fm.exists()


def test_active_scope_detection_legacy_payload_treated_as_movie(tmp_path: Path) -> None:
    fac, session = _session(tmp_path)
    assert refiner_file_remux_pass_job_active_for_scope(session, media_scope="movie") is False
    assert refiner_file_remux_pass_job_active_for_scope(session, media_scope="tv") is False
    session.add(
        RefinerJob(
            dedupe_key="r1",
            job_kind=REFINER_FILE_REMUX_PASS_JOB_KIND,
            payload_json=json.dumps({"relative_media_path": "x.mkv", "dry_run": True}),
            status=RefinerJobStatus.PENDING.value,
            max_attempts=3,
        ),
    )
    session.commit()
    assert refiner_file_remux_pass_job_active_for_scope(session, media_scope="movie") is True
    assert refiner_file_remux_pass_job_active_for_scope(session, media_scope="tv") is False
    with fac() as s2:
        s2.execute(delete(RefinerJob))
        s2.commit()


def test_shared_resolved_work_root_blocks_deletes_both_scopes(tmp_path: Path) -> None:
    _, session = _session(tmp_path)
    shared = tmp_path / "shared"
    shared.mkdir()
    f = shared / "x.refiner.shared.mkv"
    f.write_bytes(b"x")
    old = time.time() - 200_000
    os.utime(f, (old, old))
    settings = _settings(min_stale=0)
    with _patch_roots(shared, shared):
        out_m = run_refiner_work_temp_stale_sweep_for_scope(
            session=session,
            settings=settings,
            media_scope="movie",
            dry_run=False,
        )
        out_t = run_refiner_work_temp_stale_sweep_for_scope(
            session=session,
            settings=settings,
            media_scope="tv",
            dry_run=False,
        )
    assert f.exists()
    assert out_m["temp_cleanup_shared_work_root_conflict"] is True
    assert out_t["temp_cleanup_shared_work_root_conflict"] is True
    assert out_m["temp_cleanup_ran"] is False
    assert out_t["temp_cleanup_ran"] is False
    assert out_m["temp_cleanup_skipped_reason"]
    assert out_t["temp_cleanup_skipped_reason"]


def test_dry_run_deletes_nothing_movie_scope(tmp_path: Path) -> None:
    _, session = _session(tmp_path)
    w_m = tmp_path / "m"
    w_t = tmp_path / "t"
    w_m.mkdir()
    w_t.mkdir()
    f = w_m / "z.refiner.dry.mkv"
    f.write_bytes(b"z")
    old = time.time() - 200_000
    os.utime(f, (old, old))
    settings = _settings(min_stale=0)
    with _patch_roots(w_m, w_t):
        out = run_refiner_work_temp_stale_sweep_for_scope(
            session=session,
            settings=settings,
            media_scope="movie",
            dry_run=True,
        )
    assert f.exists()
    assert out["temp_cleanup_dry_run"] is True
    assert out["temp_cleanup_files_deleted"] == []
    assert out["temp_cleanup_candidates_found"] == 1


def test_file_lock_skip_continues_movie_scope(tmp_path: Path) -> None:
    _, session = _session(tmp_path)
    w_m = tmp_path / "m"
    w_t = tmp_path / "t"
    w_m.mkdir()
    w_t.mkdir()
    f1 = w_m / "a.refiner.1.mkv"
    f2 = w_m / "b.refiner.2.mkv"
    f1.write_bytes(b"1")
    f2.write_bytes(b"2")
    old = time.time() - 200_000
    os.utime(f1, (old, old))
    os.utime(f2, (old, old))
    settings = _settings(min_stale=0)
    real_unlink = Path.unlink

    def _unlink(self: Path, *a, **kw):
        if self.resolve() == f1.resolve():
            raise PermissionError("locked")
        return real_unlink(self, *a, **kw)

    with _patch_roots(w_m, w_t):
        with patch.object(Path, "unlink", _unlink):
            out = run_refiner_work_temp_stale_sweep_for_scope(
                session=session,
                settings=settings,
                media_scope="movie",
                dry_run=False,
            )
    assert f1.exists()
    assert not f2.exists()
    assert len(out["temp_cleanup_files_deleted"]) == 1


def test_activity_field_keys_include_scope_and_conflict_flag(tmp_path: Path) -> None:
    _, session = _session(tmp_path)
    w_m = tmp_path / "m"
    w_t = tmp_path / "t"
    w_m.mkdir()
    w_t.mkdir()
    settings = _settings(min_stale=0)
    with _patch_roots(w_m, w_t):
        out = run_refiner_work_temp_stale_sweep_for_scope(
            session=session,
            settings=settings,
            media_scope="tv",
            dry_run=False,
        )
    for k in (
        "media_scope",
        "temp_cleanup_ran",
        "temp_cleanup_skipped_reason",
        "temp_cleanup_root_paths",
        "temp_cleanup_candidates_found",
        "temp_cleanup_files_deleted",
        "temp_cleanup_files_skipped",
        "temp_cleanup_dry_run",
        "temp_cleanup_shared_work_root_conflict",
    ):
        assert k in out
    assert out["media_scope"] == "tv"


def test_enqueue_movie_and_tv_produce_two_dedupe_rows(tmp_path: Path) -> None:
    _, session = _session(tmp_path)
    enqueue_refiner_work_temp_stale_sweep_job(session, media_scope="movie")
    enqueue_refiner_work_temp_stale_sweep_job(session, media_scope="tv")
    session.commit()
    rows = session.scalars(select(RefinerJob)).all()
    assert len(rows) == 2
    keys = {r.dedupe_key for r in rows}
    assert keys == {REFINER_WORK_TEMP_STALE_SWEEP_DEDUPE_KEY_MOVIE, REFINER_WORK_TEMP_STALE_SWEEP_DEDUPE_KEY_TV}


def test_shared_min_stale_age_used_for_both_scopes(tmp_path: Path) -> None:
    """Narrow exception: one min_stale_age setting applies to movie and tv sweeps."""
    _, session = _session(tmp_path)
    w_m = tmp_path / "m"
    w_t = tmp_path / "t"
    w_m.mkdir()
    w_t.mkdir()
    f = w_t / "t.refiner.age.mkv"
    f.write_bytes(b"1")
    os.utime(f, (time.time() - 500, time.time() - 500))
    settings = _settings(min_stale=10_000)
    with _patch_roots(w_m, w_t):
        out = run_refiner_work_temp_stale_sweep_for_scope(
            session=session,
            settings=settings,
            media_scope="tv",
            dry_run=False,
        )
    assert f.exists()
    assert out["temp_cleanup_candidates_found"] == 1
    assert any("not stale enough" in s for s in out["temp_cleanup_files_skipped"])
