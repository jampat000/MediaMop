"""Unit tests for watched-folder scan filesystem helpers and duplicate guards."""

from __future__ import annotations

import json

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from mediamop.core.db import Base
from mediamop.modules.refiner.jobs_model import RefinerJob, RefinerJobStatus
from mediamop.modules.refiner.refiner_file_remux_pass_job_kinds import REFINER_FILE_REMUX_PASS_JOB_KIND
from mediamop.modules.refiner.refiner_watched_folder_remux_scan_dispatch_ops import (
    iter_watched_folder_media_candidate_files,
    refiner_active_remux_pass_exists_for_relative_path,
    refiner_completed_remux_output_exists_for_relative_path,
    relative_posix_path_under_watched,
    retry_completed_movie_source_cleanup,
)
from mediamop.platform.activity.models import ActivityEvent

import mediamop.modules.refiner.jobs_model  # noqa: F401
import mediamop.platform.activity.models  # noqa: F401


def test_iter_watched_folder_media_candidates_sorted(tmp_path) -> None:
    w = tmp_path / "w"
    w.mkdir()
    (w / "b.mkv").write_bytes(b"x")
    (w / "a.mkv").write_bytes(b"x")
    (w / "skip.txt").write_bytes(b"n")
    got = iter_watched_folder_media_candidate_files(w)
    assert [p.name for p in got] == ["a.mkv", "b.mkv"]


def test_relative_posix_under_watched(tmp_path) -> None:
    w = tmp_path / "root"
    w.mkdir()
    sub = w / "sub"
    sub.mkdir()
    f = sub / "f.mkv"
    f.write_bytes(b"1")
    assert relative_posix_path_under_watched(watched_root=w, file_path=f) == "sub/f.mkv"


def test_active_remux_detects_pending_payload_relative(tmp_path) -> None:
    url = f"sqlite:///{tmp_path / 't.sqlite'}"
    engine = create_engine(url, connect_args={"check_same_thread": False}, future=True)
    Base.metadata.create_all(engine)
    fac = sessionmaker(bind=engine, class_=Session, autoflush=False, autocommit=False, future=True)
    with fac() as s:
        s.add(
            RefinerJob(
                dedupe_key="x",
                job_kind=REFINER_FILE_REMUX_PASS_JOB_KIND,
                payload_json=json.dumps(
                    {"relative_media_path": "movies/a.mkv", "dry_run": True, "media_scope": "movie"},
                ),
                status=RefinerJobStatus.PENDING.value,
                max_attempts=3,
            ),
        )
        s.commit()
    with fac() as s:
        assert refiner_active_remux_pass_exists_for_relative_path(s, relative_posix="movies/a.mkv") is True
        assert refiner_active_remux_pass_exists_for_relative_path(s, relative_posix="other.mkv") is False
        assert (
            refiner_active_remux_pass_exists_for_relative_path(
                s,
                relative_posix="movies/a.mkv",
                media_scope="tv",
            )
            is False
        )


def test_completed_remux_output_blocks_repeat_scan_when_source_cleanup_failed(tmp_path) -> None:
    url = f"sqlite:///{tmp_path / 't.sqlite'}"
    engine = create_engine(url, connect_args={"check_same_thread": False}, future=True)
    Base.metadata.create_all(engine)
    fac = sessionmaker(bind=engine, class_=Session, autoflush=False, autocommit=False, future=True)
    output = tmp_path / "out" / "movies" / "a.mkv"
    output.parent.mkdir(parents=True)
    output.write_bytes(b"done")
    detail = {
        "ok": True,
        "outcome": "live_output_written",
        "relative_media_path": "movies/a.mkv",
        "media_scope": "movie",
        "output_file": str(output),
        "source_deleted_after_success": False,
        "source_folder_skip_reason": "file is locked",
    }
    with fac() as s:
        s.add(
            ActivityEvent(
                module="refiner",
                event_type="refiner.file_remux_pass_completed",
                title="a.mkv was processed successfully",
                detail=json.dumps(detail),
            ),
        )
        s.commit()

    with fac() as s:
        assert (
            refiner_completed_remux_output_exists_for_relative_path(
                s,
                relative_posix="movies/a.mkv",
                media_scope="movie",
            )
            is True
        )
        assert (
            refiner_completed_remux_output_exists_for_relative_path(
                s,
                relative_posix="movies/a.mkv",
                media_scope="tv",
            )
            is False
        )


def test_completed_remux_output_guard_escapes_like_wildcards(tmp_path) -> None:
    url = f"sqlite:///{tmp_path / 't.sqlite'}"
    engine = create_engine(url, connect_args={"check_same_thread": False}, future=True)
    Base.metadata.create_all(engine)
    fac = sessionmaker(bind=engine, class_=Session, autoflush=False, autocommit=False, future=True)
    output = tmp_path / "out" / "movies" / "a_b.mkv"
    output.parent.mkdir(parents=True)
    output.write_bytes(b"done")
    target_detail = {
        "ok": True,
        "relative_media_path": "movies/a_b.mkv",
        "media_scope": "movie",
        "output_file": str(output),
    }
    false_detail = {
        "ok": True,
        "relative_media_path": "movies/axb.mkv",
        "media_scope": "movie",
        "output_file": str(output),
    }
    with fac() as s:
        s.add(
            ActivityEvent(
                module="refiner",
                event_type="refiner.file_remux_pass_completed",
                title="a_b.mkv was processed successfully",
                detail=json.dumps(target_detail),
            ),
        )
        for _ in range(60):
            s.add(
                ActivityEvent(
                    module="refiner",
                    event_type="refiner.file_remux_pass_completed",
                    title="axb.mkv was processed successfully",
                    detail=json.dumps(false_detail),
                ),
            )
        s.commit()

    with fac() as s:
        assert (
            refiner_completed_remux_output_exists_for_relative_path(
                s,
                relative_posix="movies/a_b.mkv",
                media_scope="movie",
            )
            is True
        )


def test_completed_remux_output_guard_allows_reprocess_when_output_missing(tmp_path) -> None:
    url = f"sqlite:///{tmp_path / 't.sqlite'}"
    engine = create_engine(url, connect_args={"check_same_thread": False}, future=True)
    Base.metadata.create_all(engine)
    fac = sessionmaker(bind=engine, class_=Session, autoflush=False, autocommit=False, future=True)
    detail = {
        "ok": True,
        "relative_media_path": "movies/a.mkv",
        "media_scope": "movie",
        "output_file": str(tmp_path / "missing" / "a.mkv"),
        "source_deleted_after_success": False,
    }
    with fac() as s:
        s.add(
            ActivityEvent(
                module="refiner",
                event_type="refiner.file_remux_pass_completed",
                title="a.mkv was processed successfully",
                detail=json.dumps(detail),
            ),
        )
        s.commit()

    with fac() as s:
        assert (
            refiner_completed_remux_output_exists_for_relative_path(
                s,
                relative_posix="movies/a.mkv",
                media_scope="movie",
            )
            is False
        )


def test_retry_completed_movie_source_cleanup_removes_release_folder(tmp_path) -> None:
    watched = tmp_path / "watch"
    release = watched / "Movie 2026"
    release.mkdir(parents=True)
    media = release / "Movie 2026.mkv"
    media.write_bytes(b"source")
    (release / "extra.nfo").write_text("metadata", encoding="utf-8")

    ok, reason = retry_completed_movie_source_cleanup(watched_root=watched, file_path=media)

    assert ok is True
    assert reason is None
    assert not release.exists()


def test_retry_completed_movie_source_cleanup_never_removes_watched_root_file(tmp_path) -> None:
    watched = tmp_path / "watch"
    watched.mkdir()
    media = watched / "Loose Movie 2026.mkv"
    media.write_bytes(b"source")

    ok, reason = retry_completed_movie_source_cleanup(watched_root=watched, file_path=media)

    assert ok is False
    assert "watched folder root" in (reason or "")
    assert media.exists()
