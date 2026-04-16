"""Tests for Refiner Pass 3b — TV output-folder cleanup (Sonarr truth + gates)."""

from __future__ import annotations

import json
import os
import time
from dataclasses import replace
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

import mediamop.modules.refiner.jobs_model  # noqa: F401
from mediamop.core.config import MediaMopSettings
from mediamop.core.db import Base
from mediamop.modules.refiner.jobs_model import RefinerJob, RefinerJobStatus
from mediamop.modules.refiner.refiner_file_remux_pass_job_kinds import REFINER_FILE_REMUX_PASS_JOB_KIND
from mediamop.modules.refiner.refiner_path_settings_service import RefinerPathRuntime
from mediamop.modules.refiner.refiner_tv_output_cleanup import (
    iter_direct_child_refiner_media_candidates,
    maybe_run_tv_output_season_folder_cleanup_after_remux,
    normalize_relative_media_path_for_match,
)


def _session(tmp_path: Path) -> tuple[sessionmaker[Session], Session]:
    url = f"sqlite:///{tmp_path / 't.sqlite'}"
    engine = create_engine(url, connect_args={"check_same_thread": False}, future=True)
    Base.metadata.create_all(engine)
    fac = sessionmaker(bind=engine, class_=Session, autoflush=False, autocommit=False, future=True)
    return fac, fac()


def _settings(*, min_out_age: int = 0) -> MediaMopSettings:
    return replace(MediaMopSettings.load(), refiner_tv_output_cleanup_min_age_seconds=min_out_age)


def _fake_sonarr_creds(session: Session, settings: MediaMopSettings) -> tuple[str, str]:
    return "http://127.0.0.1:9", "fake-key"


def test_normalize_relative_media_path() -> None:
    assert normalize_relative_media_path_for_match("Show/S01/e.mkv") == "Show/S01/e.mkv"


def test_movie_scope_skips_with_plain_reason(tmp_path: Path) -> None:
    _, session = _session(tmp_path)
    out: dict = {}
    watched = tmp_path / "w"
    out_r = tmp_path / "o"
    watched.mkdir()
    out_r.mkdir()
    s = watched / "S01"
    s.mkdir()
    src = s / "e.mkv"
    src.write_bytes(b"x")
    rt = RefinerPathRuntime(
        watched_folder=str(watched),
        output_folder=str(out_r),
        work_folder_effective=str(tmp_path / "work"),
        work_folder_is_default=True,
    )
    maybe_run_tv_output_season_folder_cleanup_after_remux(
        session=session,
        settings=_settings(),
        path_runtime=rt,
        watched_root=watched,
        src=src,
        final_output_file=out_r / "S01" / "e.mkv",
        dry_run=False,
        relative_media_path="S01/e.mkv",
        current_job_id=1,
        media_scope="movie",
        out=out,
    )
    assert "only to TV" in (out.get("tv_output_season_folder_skip_reason") or "")


def test_truth_failed_when_sonarr_episodefile_inside_folder(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _, session = _session(tmp_path)
    monkeypatch.setattr(
        "mediamop.modules.refiner.refiner_tv_output_cleanup.resolve_sonarr_http_credentials",
        _fake_sonarr_creds,
    )
    ep_path = (tmp_path / "o" / "Show" / "S01" / "e.mkv").resolve()
    files = [{"id": 1, "path": str(ep_path)}]
    monkeypatch.setattr(
        "mediamop.modules.refiner.refiner_tv_output_cleanup.fetch_sonarr_library_episodefiles",
        lambda **kwargs: files,
    )
    watched = tmp_path / "w"
    out_root = tmp_path / "o"
    season = out_root / "Show" / "S01"
    season.mkdir(parents=True)
    f = season / "e.mkv"
    f.write_bytes(b"x")
    old = time.time() - 200_000
    os.utime(f, (old, old))
    watched.mkdir()
    src = watched / "Show" / "S01" / "e.mkv"
    src.parent.mkdir(parents=True)
    src.write_bytes(b"y")
    rt = RefinerPathRuntime(
        watched_folder=str(watched),
        output_folder=str(out_root),
        work_folder_effective=str(tmp_path / "work"),
        work_folder_is_default=True,
    )
    out: dict = {}
    maybe_run_tv_output_season_folder_cleanup_after_remux(
        session=session,
        settings=_settings(min_out_age=60),
        path_runtime=rt,
        watched_root=watched,
        src=src,
        final_output_file=f,
        dry_run=False,
        relative_media_path="Show/S01/e.mkv",
        current_job_id=1,
        media_scope="tv",
        out=out,
    )
    assert season.exists()
    assert out["tv_output_truth_check"] == "failed"
    assert "Sonarr still reports" in (out.get("tv_output_truth_note") or "")


def test_truth_pass_deletes_season_and_cascades_show(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _, session = _session(tmp_path)
    monkeypatch.setattr(
        "mediamop.modules.refiner.refiner_tv_output_cleanup.resolve_sonarr_http_credentials",
        _fake_sonarr_creds,
    )
    monkeypatch.setattr(
        "mediamop.modules.refiner.refiner_tv_output_cleanup.fetch_sonarr_library_episodefiles",
        lambda **kwargs: [],
    )
    watched = tmp_path / "w"
    out_root = tmp_path / "o"
    season = out_root / "Show" / "S01"
    season.mkdir(parents=True)
    f = season / "e.mkv"
    f.write_bytes(b"x")
    old = time.time() - 200_000
    os.utime(f, (old, old))
    watched.mkdir()
    src = watched / "Show" / "S01" / "e.mkv"
    src.parent.mkdir(parents=True)
    src.write_bytes(b"y")
    rt = RefinerPathRuntime(
        watched_folder=str(watched),
        output_folder=str(out_root),
        work_folder_effective=str(tmp_path / "work"),
        work_folder_is_default=True,
    )
    out: dict = {}
    maybe_run_tv_output_season_folder_cleanup_after_remux(
        session=session,
        settings=_settings(min_out_age=60),
        path_runtime=rt,
        watched_root=watched,
        src=src,
        final_output_file=f,
        dry_run=False,
        relative_media_path="Show/S01/e.mkv",
        current_job_id=1,
        media_scope="tv",
        out=out,
    )
    assert out["tv_output_season_folder_deleted"] is True
    assert out["tv_output_truth_check"] == "passed"
    assert not season.exists()
    assert not (out_root / "Show").exists()
    cascade = out.get("tv_output_cascade_folders_deleted") or []
    assert any("Show" in str(p) for p in cascade)


def test_sonarr_unreachable_skips(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _, session = _session(tmp_path)
    monkeypatch.setattr(
        "mediamop.modules.refiner.refiner_tv_output_cleanup.resolve_sonarr_http_credentials",
        _fake_sonarr_creds,
    )

    def _boom(**_kwargs: object) -> list[dict[str, object]]:
        raise RuntimeError("connection refused")

    monkeypatch.setattr(
        "mediamop.modules.refiner.refiner_tv_output_cleanup.fetch_sonarr_library_episodefiles",
        _boom,
    )
    watched = tmp_path / "w"
    out_root = tmp_path / "o"
    season = out_root / "T" / "S01"
    season.mkdir(parents=True)
    f = season / "a.mkv"
    f.write_bytes(b"x")
    old = time.time() - 200_000
    os.utime(f, (old, old))
    watched.mkdir()
    src = watched / "T" / "S01" / "a.mkv"
    src.parent.mkdir(parents=True)
    src.write_bytes(b"y")
    rt = RefinerPathRuntime(
        watched_folder=str(watched),
        output_folder=str(out_root),
        work_folder_effective=str(tmp_path / "work"),
        work_folder_is_default=True,
    )
    out: dict = {}
    maybe_run_tv_output_season_folder_cleanup_after_remux(
        session=session,
        settings=_settings(min_out_age=60),
        path_runtime=rt,
        watched_root=watched,
        src=src,
        final_output_file=f,
        dry_run=False,
        relative_media_path="T/S01/a.mkv",
        current_job_id=1,
        media_scope="tv",
        out=out,
    )
    assert season.exists()
    assert out["tv_output_truth_check"] == "skipped"


def test_too_young_by_direct_child_episode_skips(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _, session = _session(tmp_path)
    monkeypatch.setattr(
        "mediamop.modules.refiner.refiner_tv_output_cleanup.resolve_sonarr_http_credentials",
        _fake_sonarr_creds,
    )
    monkeypatch.setattr(
        "mediamop.modules.refiner.refiner_tv_output_cleanup.fetch_sonarr_library_episodefiles",
        lambda **kwargs: [],
    )
    watched = tmp_path / "w"
    out_root = tmp_path / "o"
    season = out_root / "T" / "S01"
    season.mkdir(parents=True)
    f = season / "a.mkv"
    f.write_bytes(b"x")
    watched.mkdir()
    src = watched / "T" / "S01" / "a.mkv"
    src.parent.mkdir(parents=True)
    src.write_bytes(b"y")
    rt = RefinerPathRuntime(
        watched_folder=str(watched),
        output_folder=str(out_root),
        work_folder_effective=str(tmp_path / "work"),
        work_folder_is_default=True,
    )
    out: dict = {}
    maybe_run_tv_output_season_folder_cleanup_after_remux(
        session=session,
        settings=_settings(min_out_age=999_999),
        path_runtime=rt,
        watched_root=watched,
        src=src,
        final_output_file=f,
        dry_run=False,
        relative_media_path="T/S01/a.mkv",
        current_job_id=1,
        media_scope="tv",
        out=out,
    )
    assert season.exists()
    assert "too recently" in (out.get("tv_output_season_folder_skip_reason") or "").lower()


def test_age_gate_uses_direct_child_only_not_subfolder_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Fresh file only under Subs/ must not block: age gate ignores non-direct-child paths."""

    _, session = _session(tmp_path)
    monkeypatch.setattr(
        "mediamop.modules.refiner.refiner_tv_output_cleanup.resolve_sonarr_http_credentials",
        _fake_sonarr_creds,
    )
    monkeypatch.setattr(
        "mediamop.modules.refiner.refiner_tv_output_cleanup.fetch_sonarr_library_episodefiles",
        lambda **kwargs: [],
    )
    watched = tmp_path / "w"
    out_root = tmp_path / "o"
    season = out_root / "T" / "S01"
    season.mkdir(parents=True)
    ep = season / "a.mkv"
    ep.write_bytes(b"x")
    old = time.time() - 200_000
    os.utime(ep, (old, old))
    subs = season / "Subs"
    subs.mkdir()
    fresh = subs / "b.mkv"
    fresh.write_bytes(b"n")
    watched.mkdir()
    src = watched / "T" / "S01" / "a.mkv"
    src.parent.mkdir(parents=True)
    src.write_bytes(b"y")
    rt = RefinerPathRuntime(
        watched_folder=str(watched),
        output_folder=str(out_root),
        work_folder_effective=str(tmp_path / "work"),
        work_folder_is_default=True,
    )
    out: dict = {}
    maybe_run_tv_output_season_folder_cleanup_after_remux(
        session=session,
        settings=_settings(min_out_age=60),
        path_runtime=rt,
        watched_root=watched,
        src=src,
        final_output_file=ep,
        dry_run=False,
        relative_media_path="T/S01/a.mkv",
        current_job_id=1,
        media_scope="tv",
        out=out,
    )
    assert out["tv_output_season_folder_deleted"] is True
    assert not season.exists()


def test_no_direct_child_media_skips(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Season folder has nested media only (no direct-child episode files) — age gate cannot run."""

    _, session = _session(tmp_path)
    monkeypatch.setattr(
        "mediamop.modules.refiner.refiner_tv_output_cleanup.resolve_sonarr_http_credentials",
        _fake_sonarr_creds,
    )
    watched = tmp_path / "w"
    out_root = tmp_path / "o"
    season = out_root / "T" / "S01"
    season.mkdir(parents=True)
    subs = season / "Subs"
    subs.mkdir()
    (subs / "x.mkv").write_bytes(b"x")
    watched.mkdir()
    src = watched / "T" / "S01" / "a.mkv"
    src.parent.mkdir(parents=True)
    src.write_bytes(b"y")
    rt = RefinerPathRuntime(
        watched_folder=str(watched),
        output_folder=str(out_root),
        work_folder_effective=str(tmp_path / "work"),
        work_folder_is_default=True,
    )
    out: dict = {}
    maybe_run_tv_output_season_folder_cleanup_after_remux(
        session=session,
        settings=_settings(min_out_age=0),
        path_runtime=rt,
        watched_root=watched,
        src=src,
        final_output_file=season / "a.mkv",
        dry_run=False,
        relative_media_path="T/S01/a.mkv",
        current_job_id=1,
        media_scope="tv",
        out=out,
    )
    assert "direct child" in (out.get("tv_output_season_folder_skip_reason") or "").lower()
    assert season.exists()


def test_iter_direct_child_skips_nested_subfolder_files(tmp_path: Path) -> None:
    season = tmp_path / "S01"
    season.mkdir()
    (season / "e.mkv").write_bytes(b"1")
    (season / "Subs").mkdir()
    (season / "Subs" / "sub.mkv").write_bytes(b"2")
    names = {p.name for p in iter_direct_child_refiner_media_candidates(season)}
    assert names == {"e.mkv"}


def test_active_tv_job_same_season_blocks(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _, session = _session(tmp_path)
    monkeypatch.setattr(
        "mediamop.modules.refiner.refiner_tv_output_cleanup.resolve_sonarr_http_credentials",
        _fake_sonarr_creds,
    )
    monkeypatch.setattr(
        "mediamop.modules.refiner.refiner_tv_output_cleanup.fetch_sonarr_library_episodefiles",
        lambda **kwargs: [],
    )
    watched = tmp_path / "w"
    out_root = tmp_path / "o"
    season = out_root / "Serie" / "S01"
    season.mkdir(parents=True)
    f = season / "e.mkv"
    f.write_bytes(b"x")
    old = time.time() - 200_000
    os.utime(f, (old, old))
    watched.mkdir()
    src = watched / "Serie" / "S01" / "e.mkv"
    src.parent.mkdir(parents=True)
    src.write_bytes(b"y")
    session.add(
        RefinerJob(
            dedupe_key="k1",
            job_kind=REFINER_FILE_REMUX_PASS_JOB_KIND,
            payload_json=json.dumps(
                {"relative_media_path": "Serie/S01/other.mkv", "dry_run": False, "media_scope": "tv"},
            ),
            status=RefinerJobStatus.PENDING.value,
            max_attempts=3,
        ),
    )
    session.commit()
    rt = RefinerPathRuntime(
        watched_folder=str(watched),
        output_folder=str(out_root),
        work_folder_effective=str(tmp_path / "work"),
        work_folder_is_default=True,
    )
    out: dict = {}
    maybe_run_tv_output_season_folder_cleanup_after_remux(
        session=session,
        settings=_settings(min_out_age=60),
        path_runtime=rt,
        watched_root=watched,
        src=src,
        final_output_file=f,
        dry_run=False,
        relative_media_path="Serie/S01/e.mkv",
        current_job_id=999,
        media_scope="tv",
        out=out,
    )
    assert season.exists()
    assert "same season folder" in (out.get("tv_output_season_folder_skip_reason") or "").lower()


def test_active_movie_job_does_not_block_tv_output(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _, session = _session(tmp_path)
    monkeypatch.setattr(
        "mediamop.modules.refiner.refiner_tv_output_cleanup.resolve_sonarr_http_credentials",
        _fake_sonarr_creds,
    )
    monkeypatch.setattr(
        "mediamop.modules.refiner.refiner_tv_output_cleanup.fetch_sonarr_library_episodefiles",
        lambda **kwargs: [],
    )
    watched = tmp_path / "w"
    out_root = tmp_path / "o"
    season = out_root / "Serie" / "S01"
    season.mkdir(parents=True)
    f = season / "e.mkv"
    f.write_bytes(b"x")
    old = time.time() - 200_000
    os.utime(f, (old, old))
    watched.mkdir()
    src = watched / "Serie" / "S01" / "e.mkv"
    src.parent.mkdir(parents=True)
    src.write_bytes(b"y")
    session.add(
        RefinerJob(
            dedupe_key="km",
            job_kind=REFINER_FILE_REMUX_PASS_JOB_KIND,
            payload_json=json.dumps(
                {"relative_media_path": "Serie/S01/e.mkv", "dry_run": False, "media_scope": "movie"},
            ),
            status=RefinerJobStatus.PENDING.value,
            max_attempts=3,
        ),
    )
    session.commit()
    rt = RefinerPathRuntime(
        watched_folder=str(watched),
        output_folder=str(out_root),
        work_folder_effective=str(tmp_path / "work"),
        work_folder_is_default=True,
    )
    out: dict = {}
    maybe_run_tv_output_season_folder_cleanup_after_remux(
        session=session,
        settings=_settings(min_out_age=60),
        path_runtime=rt,
        watched_root=watched,
        src=src,
        final_output_file=f,
        dry_run=False,
        relative_media_path="Serie/S01/e.mkv",
        current_job_id=1,
        media_scope="tv",
        out=out,
    )
    assert out["tv_output_season_folder_deleted"] is True


def test_dry_run_skips_entirely_no_sonarr(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _, session = _session(tmp_path)
    calls: list[int] = []

    def _no(**_kwargs: object) -> list[dict[str, object]]:
        calls.append(1)
        return []

    monkeypatch.setattr(
        "mediamop.modules.refiner.refiner_tv_output_cleanup.resolve_sonarr_http_credentials",
        _fake_sonarr_creds,
    )
    monkeypatch.setattr(
        "mediamop.modules.refiner.refiner_tv_output_cleanup.fetch_sonarr_library_episodefiles",
        _no,
    )
    watched = tmp_path / "w"
    out_root = tmp_path / "o"
    season = out_root / "T" / "S01"
    season.mkdir(parents=True)
    f = season / "a.mkv"
    f.write_bytes(b"x")
    watched.mkdir()
    src = watched / "T" / "S01" / "a.mkv"
    src.parent.mkdir(parents=True)
    src.write_bytes(b"y")
    rt = RefinerPathRuntime(
        watched_folder=str(watched),
        output_folder=str(out_root),
        work_folder_effective=str(tmp_path / "work"),
        work_folder_is_default=True,
    )
    out: dict = {}
    maybe_run_tv_output_season_folder_cleanup_after_remux(
        session=session,
        settings=_settings(),
        path_runtime=rt,
        watched_root=watched,
        src=src,
        final_output_file=f,
        dry_run=True,
        relative_media_path="T/S01/a.mkv",
        current_job_id=1,
        media_scope="tv",
        out=out,
    )
    assert season.exists()
    assert calls == []
    assert out["tv_output_truth_check"] == "skipped"
    assert "dry run" in (out.get("tv_output_season_folder_skip_reason") or "").lower()


def test_rmtree_failure_skips(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _, session = _session(tmp_path)
    monkeypatch.setattr(
        "mediamop.modules.refiner.refiner_tv_output_cleanup.resolve_sonarr_http_credentials",
        _fake_sonarr_creds,
    )
    monkeypatch.setattr(
        "mediamop.modules.refiner.refiner_tv_output_cleanup.fetch_sonarr_library_episodefiles",
        lambda **kwargs: [],
    )

    def _boom(path: str | Path, *a: object, **k: object) -> None:
        raise PermissionError(13, "locked", str(path))

    monkeypatch.setattr("mediamop.modules.refiner.refiner_tv_output_cleanup.shutil.rmtree", _boom)
    watched = tmp_path / "w"
    out_root = tmp_path / "o"
    season = out_root / "T" / "S01"
    season.mkdir(parents=True)
    f = season / "a.mkv"
    f.write_bytes(b"x")
    old = time.time() - 200_000
    os.utime(f, (old, old))
    watched.mkdir()
    src = watched / "T" / "S01" / "a.mkv"
    src.parent.mkdir(parents=True)
    src.write_bytes(b"y")
    rt = RefinerPathRuntime(
        watched_folder=str(watched),
        output_folder=str(out_root),
        work_folder_effective=str(tmp_path / "work"),
        work_folder_is_default=True,
    )
    out: dict = {}
    maybe_run_tv_output_season_folder_cleanup_after_remux(
        session=session,
        settings=_settings(min_out_age=60),
        path_runtime=rt,
        watched_root=watched,
        src=src,
        final_output_file=f,
        dry_run=False,
        relative_media_path="T/S01/a.mkv",
        current_job_id=1,
        media_scope="tv",
        out=out,
    )
    assert season.exists()
    assert "could not remove" in (out.get("tv_output_season_folder_skip_reason") or "").lower()


def test_expected_output_outside_output_root_skips(tmp_path: Path) -> None:
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
    maybe_run_tv_output_season_folder_cleanup_after_remux(
        session=session,
        settings=_settings(min_out_age=0),
        path_runtime=rt,
        watched_root=watched,
        src=src,
        final_output_file=fake_out,
        dry_run=False,
        relative_media_path="a.mkv",
        current_job_id=1,
        media_scope="tv",
        out=out,
    )
    assert "outside" in (out.get("tv_output_season_folder_skip_reason") or "").lower()


def test_season_folder_is_output_root_skips(tmp_path: Path) -> None:
    _, session = _session(tmp_path)
    watched = tmp_path / "w"
    out_root = tmp_path / "o"
    watched.mkdir()
    out_root.mkdir()
    src = watched / "file.mkv"
    src.write_bytes(b"x")
    out_ep = out_root / "file.mkv"
    out_ep.write_bytes(b"y")
    rt = RefinerPathRuntime(
        watched_folder=str(watched),
        output_folder=str(out_root),
        work_folder_effective=str(tmp_path / "work"),
        work_folder_is_default=True,
    )
    out: dict = {}
    maybe_run_tv_output_season_folder_cleanup_after_remux(
        session=session,
        settings=_settings(),
        path_runtime=rt,
        watched_root=watched,
        src=src,
        final_output_file=out_ep,
        dry_run=False,
        relative_media_path="file.mkv",
        current_job_id=1,
        media_scope="tv",
        out=out,
    )
    assert "output folder root" in (out.get("tv_output_season_folder_skip_reason") or "").lower()
    assert out_ep.exists()


def test_cascade_stops_at_output_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _, session = _session(tmp_path)
    monkeypatch.setattr(
        "mediamop.modules.refiner.refiner_tv_output_cleanup.resolve_sonarr_http_credentials",
        _fake_sonarr_creds,
    )
    monkeypatch.setattr(
        "mediamop.modules.refiner.refiner_tv_output_cleanup.fetch_sonarr_library_episodefiles",
        lambda **kwargs: [],
    )
    watched = tmp_path / "w"
    out_root = tmp_path / "o"
    out_root.mkdir()
    lib = out_root / "Lib"
    lib.mkdir()
    (lib / "keep.txt").write_bytes(b"x")
    season = lib / "Show" / "S01"
    season.mkdir(parents=True)
    f = season / "e.mkv"
    f.write_bytes(b"x")
    old = time.time() - 200_000
    os.utime(f, (old, old))
    watched.mkdir()
    src = watched / "Lib" / "Show" / "S01" / "e.mkv"
    src.parent.mkdir(parents=True)
    src.write_bytes(b"y")
    rt = RefinerPathRuntime(
        watched_folder=str(watched),
        output_folder=str(out_root),
        work_folder_effective=str(tmp_path / "work"),
        work_folder_is_default=True,
    )
    out: dict = {}
    maybe_run_tv_output_season_folder_cleanup_after_remux(
        session=session,
        settings=_settings(min_out_age=60),
        path_runtime=rt,
        watched_root=watched,
        src=src,
        final_output_file=f,
        dry_run=False,
        relative_media_path="Lib/Show/S01/e.mkv",
        current_job_id=1,
        media_scope="tv",
        out=out,
    )
    assert out["tv_output_season_folder_deleted"] is True
    assert (out_root / "Lib").is_dir()
    cascade = [Path(p) for p in (out.get("tv_output_cascade_folders_deleted") or [])]
    assert not any(p.resolve() == out_root.resolve() for p in cascade)


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
    )
    out: dict = {}
    maybe_run_tv_output_season_folder_cleanup_after_remux(
        session=session,
        settings=_settings(),
        path_runtime=rt,
        watched_root=watched,
        src=src,
        final_output_file=None,
        dry_run=True,
        relative_media_path="a.mkv",
        current_job_id=1,
        media_scope="tv",
        out=out,
    )
    for k in (
        "tv_output_season_folder_deleted",
        "tv_output_season_folder_path",
        "tv_output_season_folder_skip_reason",
        "tv_output_truth_check",
        "tv_output_truth_note",
        "tv_output_age_seconds",
        "tv_output_cascade_folders_deleted",
        "tv_output_dry_run",
    ):
        assert k in out
