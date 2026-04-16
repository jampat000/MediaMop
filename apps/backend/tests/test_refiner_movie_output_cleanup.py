"""Tests for Refiner Pass 3a — Movies output-folder cleanup (Radarr truth + gates)."""

from __future__ import annotations

import json
import os
import time
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine, delete
from sqlalchemy.orm import Session, sessionmaker

import mediamop.modules.refiner.jobs_model  # noqa: F401
from mediamop.core.config import MediaMopSettings
from mediamop.core.db import Base
from mediamop.modules.refiner.jobs_model import RefinerJob, RefinerJobStatus
from mediamop.modules.refiner.refiner_file_remux_pass_job_kinds import REFINER_FILE_REMUX_PASS_JOB_KIND
from mediamop.modules.refiner.refiner_movie_output_cleanup import (
    maybe_run_movie_output_folder_cleanup_after_remux,
    normalize_relative_media_path_for_match,
)
from mediamop.modules.refiner.refiner_path_settings_service import RefinerPathRuntime


def _session(tmp_path: Path) -> tuple[sessionmaker[Session], Session]:
    url = f"sqlite:///{tmp_path / 't.sqlite'}"
    engine = create_engine(url, connect_args={"check_same_thread": False}, future=True)
    Base.metadata.create_all(engine)
    fac = sessionmaker(bind=engine, class_=Session, autoflush=False, autocommit=False, future=True)
    return fac, fac()


def _settings(*, min_out_age: int = 0) -> MediaMopSettings:
    return replace(MediaMopSettings.load(), refiner_movie_output_cleanup_min_age_seconds=min_out_age)


def _fake_radarr_creds(session: Session, settings: MediaMopSettings) -> tuple[str, str]:
    return "http://127.0.0.1:9", "fake-key"


def test_normalize_relative_media_path() -> None:
    assert normalize_relative_media_path_for_match("foo/bar.mkv") == "foo/bar.mkv"
    assert normalize_relative_media_path_for_match(".\\foo\\bar.mkv") == "foo/bar.mkv"


def test_tv_scope_skips_with_plain_reason(tmp_path: Path) -> None:
    _, session = _session(tmp_path)
    out: dict = {}
    watched = tmp_path / "w"
    out_r = tmp_path / "o"
    watched.mkdir()
    out_r.mkdir()
    src = watched / "m.mkv"
    src.write_bytes(b"x")
    rt = RefinerPathRuntime(
        watched_folder=str(watched),
        output_folder=str(out_r),
        work_folder_effective=str(tmp_path / "work"),
        work_folder_is_default=True,
    )
    maybe_run_movie_output_folder_cleanup_after_remux(
        session=session,
        settings=_settings(),
        path_runtime=rt,
        watched_root=watched,
        src=src,
        final_output_file=out_r / "m.mkv",
        dry_run=False,
        relative_media_path="m.mkv",
        current_job_id=1,
        media_scope="tv",
        out=out,
    )
    assert "TV output cleanup is separate" in (out.get("movie_output_folder_skip_reason") or "")


def test_truth_failed_when_radarr_moviefile_inside_folder(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    fac, session = _session(tmp_path)
    monkeypatch.setattr(
        "mediamop.modules.refiner.refiner_movie_output_cleanup.resolve_radarr_http_credentials",
        _fake_radarr_creds,
    )
    movies = [{"id": 1, "movieFile": {"path": str((tmp_path / "o" / "Title" / "f.mkv").resolve())}}]
    monkeypatch.setattr(
        "mediamop.modules.refiner.refiner_movie_output_cleanup.fetch_radarr_library_movies",
        lambda **kwargs: movies,
    )
    watched = tmp_path / "w"
    out_root = tmp_path / "o"
    title = out_root / "Title"
    title.mkdir(parents=True)
    f = title / "f.mkv"
    f.write_bytes(b"x")
    old = time.time() - 200_000
    os.utime(f, (old, old))
    watched.mkdir()
    src = watched / "Title" / "f.mkv"
    src.parent.mkdir(parents=True)
    src.write_bytes(b"y")
    rt = RefinerPathRuntime(
        watched_folder=str(watched),
        output_folder=str(out_root),
        work_folder_effective=str(tmp_path / "work"),
        work_folder_is_default=True,
    )
    out: dict = {}
    maybe_run_movie_output_folder_cleanup_after_remux(
        session=session,
        settings=_settings(min_out_age=60),
        path_runtime=rt,
        watched_root=watched,
        src=src,
        final_output_file=f,
        dry_run=False,
        relative_media_path="Title/f.mkv",
        current_job_id=1,
        media_scope="movie",
        out=out,
    )
    assert out["movie_output_truth_check"] == "failed"
    assert title.exists()


def test_deleted_when_radarr_empty_and_age_ok(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _, session = _session(tmp_path)
    monkeypatch.setattr(
        "mediamop.modules.refiner.refiner_movie_output_cleanup.resolve_radarr_http_credentials",
        _fake_radarr_creds,
    )
    monkeypatch.setattr(
        "mediamop.modules.refiner.refiner_movie_output_cleanup.fetch_radarr_library_movies",
        lambda **kwargs: [],
    )
    watched = tmp_path / "w"
    out_root = tmp_path / "o"
    title = out_root / "Title"
    title.mkdir(parents=True)
    f = title / "f.mkv"
    f.write_bytes(b"x")
    old = time.time() - 200_000
    os.utime(f, (old, old))
    watched.mkdir()
    src = watched / "Title" / "f.mkv"
    src.parent.mkdir(parents=True)
    src.write_bytes(b"y")
    rt = RefinerPathRuntime(
        watched_folder=str(watched),
        output_folder=str(out_root),
        work_folder_effective=str(tmp_path / "work"),
        work_folder_is_default=True,
    )
    out: dict = {}
    maybe_run_movie_output_folder_cleanup_after_remux(
        session=session,
        settings=_settings(min_out_age=60),
        path_runtime=rt,
        watched_root=watched,
        src=src,
        final_output_file=f,
        dry_run=False,
        relative_media_path="Title/f.mkv",
        current_job_id=1,
        media_scope="movie",
        out=out,
    )
    assert out["movie_output_folder_deleted"] is True
    assert out["movie_output_truth_check"] == "passed"
    assert not title.exists()


def test_radarr_unreachable_skips(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _, session = _session(tmp_path)
    monkeypatch.setattr(
        "mediamop.modules.refiner.refiner_movie_output_cleanup.resolve_radarr_http_credentials",
        _fake_radarr_creds,
    )

    def _boom(**kwargs):
        raise RuntimeError("connection refused")

    monkeypatch.setattr(
        "mediamop.modules.refiner.refiner_movie_output_cleanup.fetch_radarr_library_movies",
        _boom,
    )
    watched = tmp_path / "w"
    out_root = tmp_path / "o"
    title = out_root / "T"
    title.mkdir(parents=True)
    f = title / "a.mkv"
    f.write_bytes(b"x")
    old = time.time() - 200_000
    os.utime(f, (old, old))
    watched.mkdir()
    src = watched / "T" / "a.mkv"
    src.parent.mkdir(parents=True)
    src.write_bytes(b"y")
    rt = RefinerPathRuntime(
        watched_folder=str(watched),
        output_folder=str(out_root),
        work_folder_effective=str(tmp_path / "work"),
        work_folder_is_default=True,
    )
    out: dict = {}
    maybe_run_movie_output_folder_cleanup_after_remux(
        session=session,
        settings=_settings(min_out_age=60),
        path_runtime=rt,
        watched_root=watched,
        src=src,
        final_output_file=f,
        dry_run=False,
        relative_media_path="T/a.mkv",
        current_job_id=1,
        media_scope="movie",
        out=out,
    )
    assert out["movie_output_truth_check"] == "skipped"
    assert title.exists()


def test_age_gate_blocks(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _, session = _session(tmp_path)
    monkeypatch.setattr(
        "mediamop.modules.refiner.refiner_movie_output_cleanup.resolve_radarr_http_credentials",
        _fake_radarr_creds,
    )
    monkeypatch.setattr(
        "mediamop.modules.refiner.refiner_movie_output_cleanup.fetch_radarr_library_movies",
        lambda **kwargs: [],
    )
    watched = tmp_path / "w"
    out_root = tmp_path / "o"
    title = out_root / "T"
    title.mkdir(parents=True)
    f = title / "a.mkv"
    f.write_bytes(b"x")
    watched.mkdir()
    src = watched / "T" / "a.mkv"
    src.parent.mkdir(parents=True)
    src.write_bytes(b"y")
    rt = RefinerPathRuntime(
        watched_folder=str(watched),
        output_folder=str(out_root),
        work_folder_effective=str(tmp_path / "work"),
        work_folder_is_default=True,
    )
    out: dict = {}
    maybe_run_movie_output_folder_cleanup_after_remux(
        session=session,
        settings=_settings(min_out_age=86_400),
        path_runtime=rt,
        watched_root=watched,
        src=src,
        final_output_file=f,
        dry_run=False,
        relative_media_path="T/a.mkv",
        current_job_id=1,
        media_scope="movie",
        out=out,
    )
    assert "too recently" in (out.get("movie_output_folder_skip_reason") or "").lower()
    assert title.exists()


def test_active_movies_remux_blocks(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    fac, session = _session(tmp_path)
    monkeypatch.setattr(
        "mediamop.modules.refiner.refiner_movie_output_cleanup.resolve_radarr_http_credentials",
        _fake_radarr_creds,
    )
    monkeypatch.setattr(
        "mediamop.modules.refiner.refiner_movie_output_cleanup.fetch_radarr_library_movies",
        lambda **kwargs: [],
    )
    session.add(
        RefinerJob(
            dedupe_key="other-remux",
            job_kind=REFINER_FILE_REMUX_PASS_JOB_KIND,
            payload_json=json.dumps({"relative_media_path": "T/a.mkv", "dry_run": False, "media_scope": "movie"}),
            status=RefinerJobStatus.PENDING.value,
            max_attempts=3,
        ),
    )
    session.commit()
    watched = tmp_path / "w"
    out_root = tmp_path / "o"
    title = out_root / "T"
    title.mkdir(parents=True)
    f = title / "a.mkv"
    f.write_bytes(b"x")
    old = time.time() - 200_000
    os.utime(f, (old, old))
    watched.mkdir()
    src = watched / "T" / "a.mkv"
    src.parent.mkdir(parents=True)
    src.write_bytes(b"y")
    rt = RefinerPathRuntime(
        watched_folder=str(watched),
        output_folder=str(out_root),
        work_folder_effective=str(tmp_path / "work"),
        work_folder_is_default=True,
    )
    out: dict = {}
    maybe_run_movie_output_folder_cleanup_after_remux(
        session=session,
        settings=_settings(min_out_age=60),
        path_runtime=rt,
        watched_root=watched,
        src=src,
        final_output_file=f,
        dry_run=False,
        relative_media_path="T/a.mkv",
        current_job_id=99,
        media_scope="movie",
        out=out,
    )
    assert "Another Movies Refiner" in (out.get("movie_output_folder_skip_reason") or "")
    assert title.exists()
    with fac() as s2:
        s2.execute(delete(RefinerJob))
        s2.commit()


def test_tv_remux_job_does_not_block_movies_output_cleanup(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    fac, session = _session(tmp_path)
    monkeypatch.setattr(
        "mediamop.modules.refiner.refiner_movie_output_cleanup.resolve_radarr_http_credentials",
        _fake_radarr_creds,
    )
    monkeypatch.setattr(
        "mediamop.modules.refiner.refiner_movie_output_cleanup.fetch_radarr_library_movies",
        lambda **kwargs: [],
    )
    session.add(
        RefinerJob(
            dedupe_key="tv-remux",
            job_kind=REFINER_FILE_REMUX_PASS_JOB_KIND,
            payload_json=json.dumps({"relative_media_path": "T/a.mkv", "dry_run": False, "media_scope": "tv"}),
            status=RefinerJobStatus.PENDING.value,
            max_attempts=3,
        ),
    )
    session.commit()
    watched = tmp_path / "w"
    out_root = tmp_path / "o"
    title = out_root / "T"
    title.mkdir(parents=True)
    f = title / "a.mkv"
    f.write_bytes(b"x")
    old = time.time() - 200_000
    os.utime(f, (old, old))
    watched.mkdir()
    src = watched / "T" / "a.mkv"
    src.parent.mkdir(parents=True)
    src.write_bytes(b"y")
    rt = RefinerPathRuntime(
        watched_folder=str(watched),
        output_folder=str(out_root),
        work_folder_effective=str(tmp_path / "work"),
        work_folder_is_default=True,
    )
    out: dict = {}
    maybe_run_movie_output_folder_cleanup_after_remux(
        session=session,
        settings=_settings(min_out_age=60),
        path_runtime=rt,
        watched_root=watched,
        src=src,
        final_output_file=f,
        dry_run=False,
        relative_media_path="T/a.mkv",
        current_job_id=1,
        media_scope="movie",
        out=out,
    )
    assert out["movie_output_folder_deleted"] is True
    with fac() as s2:
        s2.execute(delete(RefinerJob))
        s2.commit()


def test_cascade_removes_empty_parent(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _, session = _session(tmp_path)
    monkeypatch.setattr(
        "mediamop.modules.refiner.refiner_movie_output_cleanup.resolve_radarr_http_credentials",
        _fake_radarr_creds,
    )
    monkeypatch.setattr(
        "mediamop.modules.refiner.refiner_movie_output_cleanup.fetch_radarr_library_movies",
        lambda **kwargs: [],
    )
    watched = tmp_path / "w"
    out_root = tmp_path / "o"
    mid = out_root / "Nest"
    leaf = mid / "Leaf"
    leaf.mkdir(parents=True)
    f = leaf / "a.mkv"
    f.write_bytes(b"x")
    old = time.time() - 200_000
    os.utime(f, (old, old))
    watched.mkdir()
    src = watched / "Nest" / "Leaf" / "a.mkv"
    src.parent.mkdir(parents=True)
    src.write_bytes(b"y")
    rt = RefinerPathRuntime(
        watched_folder=str(watched),
        output_folder=str(out_root),
        work_folder_effective=str(tmp_path / "work"),
        work_folder_is_default=True,
    )
    out: dict = {}
    maybe_run_movie_output_folder_cleanup_after_remux(
        session=session,
        settings=_settings(min_out_age=60),
        path_runtime=rt,
        watched_root=watched,
        src=src,
        final_output_file=f,
        dry_run=False,
        relative_media_path="Nest/Leaf/a.mkv",
        current_job_id=1,
        media_scope="movie",
        out=out,
    )
    assert out["movie_output_folder_deleted"] is True
    assert not leaf.exists()
    cascade = out.get("movie_output_cascade_folders_deleted") or []
    assert any("Nest" in str(p) for p in cascade)


def test_output_folder_is_root_skips(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _, session = _session(tmp_path)
    monkeypatch.setattr(
        "mediamop.modules.refiner.refiner_movie_output_cleanup.resolve_radarr_http_credentials",
        _fake_radarr_creds,
    )
    monkeypatch.setattr(
        "mediamop.modules.refiner.refiner_movie_output_cleanup.fetch_radarr_library_movies",
        lambda **kwargs: [],
    )
    watched = tmp_path / "w"
    out_root = tmp_path / "o"
    out_root.mkdir()
    f = out_root / "rootfile.mkv"
    f.write_bytes(b"x")
    old = time.time() - 200_000
    os.utime(f, (old, old))
    watched.mkdir()
    src = watched / "rootfile.mkv"
    src.write_bytes(b"y")
    rt = RefinerPathRuntime(
        watched_folder=str(watched),
        output_folder=str(out_root),
        work_folder_effective=str(tmp_path / "work"),
        work_folder_is_default=True,
    )
    out: dict = {}
    maybe_run_movie_output_folder_cleanup_after_remux(
        session=session,
        settings=_settings(min_out_age=60),
        path_runtime=rt,
        watched_root=watched,
        src=src,
        final_output_file=f,
        dry_run=False,
        relative_media_path="rootfile.mkv",
        current_job_id=1,
        media_scope="movie",
        out=out,
    )
    assert "output folder root" in (out.get("movie_output_folder_skip_reason") or "").lower()
    assert f.exists()


def test_rmtree_lock_skips(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _, session = _session(tmp_path)
    monkeypatch.setattr(
        "mediamop.modules.refiner.refiner_movie_output_cleanup.resolve_radarr_http_credentials",
        _fake_radarr_creds,
    )
    monkeypatch.setattr(
        "mediamop.modules.refiner.refiner_movie_output_cleanup.fetch_radarr_library_movies",
        lambda **kwargs: [],
    )
    watched = tmp_path / "w"
    out_root = tmp_path / "o"
    title = out_root / "T"
    title.mkdir(parents=True)
    f = title / "a.mkv"
    f.write_bytes(b"x")
    old = time.time() - 200_000
    os.utime(f, (old, old))
    watched.mkdir()
    src = watched / "T" / "a.mkv"
    src.parent.mkdir(parents=True)
    src.write_bytes(b"y")
    rt = RefinerPathRuntime(
        watched_folder=str(watched),
        output_folder=str(out_root),
        work_folder_effective=str(tmp_path / "work"),
        work_folder_is_default=True,
    )
    out: dict = {}
    with patch(
        "mediamop.modules.refiner.refiner_movie_output_cleanup.shutil.rmtree",
        side_effect=PermissionError("locked"),
    ):
        maybe_run_movie_output_folder_cleanup_after_remux(
            session=session,
            settings=_settings(min_out_age=60),
            path_runtime=rt,
            watched_root=watched,
            src=src,
            final_output_file=f,
            dry_run=False,
            relative_media_path="T/a.mkv",
            current_job_id=1,
            media_scope="movie",
            out=out,
        )
    assert title.exists()
    assert "could not remove" in (out.get("movie_output_folder_skip_reason") or "").lower()


def test_dry_run_deletes_nothing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _, session = _session(tmp_path)
    radarr_calls: list[int] = []

    def _radarr_must_not_run(**_kwargs: object) -> list[dict[str, object]]:
        radarr_calls.append(1)
        return []

    monkeypatch.setattr(
        "mediamop.modules.refiner.refiner_movie_output_cleanup.resolve_radarr_http_credentials",
        _fake_radarr_creds,
    )
    monkeypatch.setattr(
        "mediamop.modules.refiner.refiner_movie_output_cleanup.fetch_radarr_library_movies",
        _radarr_must_not_run,
    )
    watched = tmp_path / "w"
    out_root = tmp_path / "o"
    title = out_root / "T"
    title.mkdir(parents=True)
    f = title / "a.mkv"
    f.write_bytes(b"x")
    old = time.time() - 200_000
    os.utime(f, (old, old))
    watched.mkdir()
    src = watched / "T" / "a.mkv"
    src.parent.mkdir(parents=True)
    src.write_bytes(b"y")
    rt = RefinerPathRuntime(
        watched_folder=str(watched),
        output_folder=str(out_root),
        work_folder_effective=str(tmp_path / "work"),
        work_folder_is_default=True,
    )
    out: dict = {}
    maybe_run_movie_output_folder_cleanup_after_remux(
        session=session,
        settings=_settings(min_out_age=60),
        path_runtime=rt,
        watched_root=watched,
        src=src,
        final_output_file=f,
        dry_run=True,
        relative_media_path="T/a.mkv",
        current_job_id=1,
        media_scope="movie",
        out=out,
    )
    assert title.exists()
    assert out["movie_output_dry_run"] is True
    assert out["movie_output_truth_check"] == "skipped"
    assert radarr_calls == []
    skip = out.get("movie_output_folder_skip_reason") or ""
    assert "dry run" in skip.lower()
    assert "radarr" in skip.lower()


def test_expected_output_outside_output_root_skips(tmp_path: Path) -> None:
    """If mapping would place media outside Movies output root, cleanup is skipped (bounds guard)."""

    _, session = _session(tmp_path)
    watched = tmp_path / "w"
    out_root = tmp_path / "o"
    watched.mkdir()
    out_root.mkdir()
    other = tmp_path / "outside_output_root"
    other.mkdir(parents=True, exist_ok=True)
    src = watched / "a.mkv"
    src.write_bytes(b"x")
    rt = RefinerPathRuntime(
        watched_folder=str(watched),
        output_folder=str(out_root),
        work_folder_effective=str(tmp_path / "work"),
        work_folder_is_default=True,
    )
    out: dict = {}
    fake_out = other / "a.mkv"
    fake_out.parent.mkdir(parents=True, exist_ok=True)
    fake_out.write_bytes(b"z")
    maybe_run_movie_output_folder_cleanup_after_remux(
        session=session,
        settings=_settings(min_out_age=0),
        path_runtime=rt,
        watched_root=watched,
        src=src,
        final_output_file=fake_out,
        dry_run=False,
        relative_media_path="a.mkv",
        current_job_id=1,
        media_scope="movie",
        out=out,
    )
    assert "outside" in (out.get("movie_output_folder_skip_reason") or "").lower()
    assert "movies output" in (out.get("movie_output_folder_skip_reason") or "").lower()


def test_activity_keys_initialized_on_skip(tmp_path: Path) -> None:
    _, session = _session(tmp_path)
    watched = tmp_path / "w"
    out_root = tmp_path / "o"
    watched.mkdir()
    out_root.mkdir()
    src = watched / "a.mkv"
    src.write_bytes(b"x")
    rt = RefinerPathRuntime(
        watched_folder=str(watched),
        output_folder="",
        work_folder_effective=str(tmp_path / "work"),
        work_folder_is_default=True,
        preview_output_folder=None,
    )
    out: dict = {}
    maybe_run_movie_output_folder_cleanup_after_remux(
        session=session,
        settings=_settings(),
        path_runtime=rt,
        watched_root=watched,
        src=src,
        final_output_file=None,
        dry_run=True,
        relative_media_path="a.mkv",
        current_job_id=1,
        media_scope="movie",
        out=out,
    )
    for k in (
        "movie_output_folder_deleted",
        "movie_output_folder_path",
        "movie_output_folder_skip_reason",
        "movie_output_truth_check",
        "movie_output_truth_note",
        "movie_output_age_seconds",
        "movie_output_cascade_folders_deleted",
        "movie_output_dry_run",
    ):
        assert k in out
