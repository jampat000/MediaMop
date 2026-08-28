"""Refusal-to-delete guards on Refiner Pass 3a (Movies output-folder cleanup).

``maybe_run_movie_output_folder_cleanup_after_remux`` ends in ``shutil.rmtree`` of a
folder in the operator's library. Everything before that is the set of reasons not to.
The happy path and the Radarr-truth refusal are covered in
``test_refiner_movie_output_cleanup.py``; this file covers the gates that were reachable
but untested, plus the cascade walk that stops parent deletion escaping the output root.

Each test asserts the folder still exists, not merely that a reason string was written.
A gate that reports a reason and deletes anyway would pass the weaker assertion.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

import mediamop.modules.refiner.jobs_model  # noqa: F401
from mediamop.core.config import MediaMopSettings
from mediamop.core.db import Base
from mediamop.modules.refiner import refiner_movie_output_cleanup as mod
from mediamop.modules.refiner.refiner_movie_output_cleanup import (
    _cascade_delete_empty_parents_under_output_root,
    maybe_run_movie_output_folder_cleanup_after_remux,
    newest_mtime_seconds_under_tree,
)
from mediamop.modules.refiner.refiner_path_settings_service import RefinerPathRuntime


def _session(tmp_path: Path) -> Session:
    engine = create_engine(
        f"sqlite:///{tmp_path / 'guards.sqlite'}",
        connect_args={"check_same_thread": False},
        future=True,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, class_=Session, autoflush=False, autocommit=False, future=True)()


def _settings(*, min_out_age: int = 0) -> MediaMopSettings:
    return replace(MediaMopSettings.load(), refiner_movie_output_cleanup_min_age_seconds=min_out_age)


def _tree(tmp_path: Path) -> tuple[Path, Path, Path, Path]:
    """watched/, output/, the source file, and the written output file."""

    watched = tmp_path / "watched"
    output = tmp_path / "output"
    (watched / "Some.Movie.2024").mkdir(parents=True)
    (output / "Some.Movie.2024").mkdir(parents=True)
    src = watched / "Some.Movie.2024" / "movie.mkv"
    src.write_bytes(b"source")
    final = output / "Some.Movie.2024" / "movie.mkv"
    final.write_bytes(b"output")
    return watched, output, src, final


def _runtime(watched: Path, output: Path, tmp_path: Path) -> RefinerPathRuntime:
    return RefinerPathRuntime(
        watched_folder=str(watched),
        output_folder=str(output),
        work_folder_effective=str(tmp_path / "work"),
        work_folder_is_default=True,
    )


def _run(session: Session, rt: RefinerPathRuntime, watched: Path, src: Path, final: Path | None) -> dict:
    out: dict = {}
    maybe_run_movie_output_folder_cleanup_after_remux(
        session=session,
        settings=_settings(),
        path_runtime=rt,
        watched_root=watched,
        src=src,
        final_output_file=final,
        relative_media_path="Some.Movie.2024/movie.mkv",
        current_job_id=1,
        media_scope="movie",
        out=out,
    )
    return out


def test_no_database_session_refuses_and_keeps_the_folder(tmp_path: Path) -> None:
    watched, output, src, final = _tree(tmp_path)
    out = _run(None, _runtime(watched, output, tmp_path), watched, src, final)  # type: ignore[arg-type]

    assert "no database session" in (out["movie_output_folder_skip_reason"] or "")
    assert out["movie_output_truth_check"] == "skipped"
    assert final.parent.is_dir(), "the output folder must survive a refusal"


def test_unconfigured_output_folder_refuses(tmp_path: Path) -> None:
    watched, output, src, final = _tree(tmp_path)
    rt = replace(_runtime(watched, output, tmp_path), output_folder="   ")
    out = _run(_session(tmp_path), rt, watched, src, final)

    assert "No Movies output folder is configured" in (out["movie_output_folder_skip_reason"] or "")
    assert final.parent.is_dir()


def test_output_folder_missing_on_disk_refuses(tmp_path: Path) -> None:
    watched, output, src, final = _tree(tmp_path)
    rt = replace(_runtime(watched, output, tmp_path), output_folder=str(tmp_path / "does-not-exist"))
    out = _run(_session(tmp_path), rt, watched, src, final)

    assert "missing on disk" in (out["movie_output_folder_skip_reason"] or "")
    assert out["movie_output_truth_check"] == "skipped"
    assert final.parent.is_dir()


def test_source_outside_the_watched_folder_refuses(tmp_path: Path) -> None:
    """A hand-off naming a path outside the watched tree must not delete anything."""

    watched, output, _src, final = _tree(tmp_path)
    stray = tmp_path / "elsewhere" / "movie.mkv"
    stray.parent.mkdir(parents=True)
    stray.write_bytes(b"x")

    out = _run(_session(tmp_path), _runtime(watched, output, tmp_path), watched, stray, final)

    assert "not under the saved Movies watched folder" in (out["movie_output_folder_skip_reason"] or "")
    assert final.parent.is_dir()
    assert stray.exists()


def test_output_file_directly_in_the_output_root_refuses(tmp_path: Path) -> None:
    """Without a per-title folder there is nothing safe to remove."""

    watched = tmp_path / "watched"
    output = tmp_path / "output"
    watched.mkdir()
    output.mkdir()
    src = watched / "movie.mkv"
    src.write_bytes(b"source")
    final = output / "movie.mkv"
    final.write_bytes(b"output")

    out = _run(_session(tmp_path), _runtime(watched, output, tmp_path), watched, src, final)

    assert "directly in the Movies output folder root" in (out["movie_output_folder_skip_reason"] or "")
    assert final.exists()


def test_unreadable_timestamps_refuse_for_safety(tmp_path: Path) -> None:
    """An output folder with no readable files gives no age to gate on, so nothing is removed."""

    watched, output, src, final = _tree(tmp_path)
    final.unlink()  # folder now has no files, so newest mtime is unknown

    out = _run(_session(tmp_path), _runtime(watched, output, tmp_path), watched, src, final)

    assert "could not read file timestamps" in (out["movie_output_folder_skip_reason"] or "")
    assert out["movie_output_truth_check"] == "skipped"
    assert final.parent.is_dir()


def test_missing_manager_credentials_leave_the_folder_in_place(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No credentials means no library truth, and no library truth means no deletion.

    This is the gate that matters most: unverifiable must never read as safe.
    """

    watched, output, src, final = _tree(tmp_path)
    monkeypatch.setattr(mod, "resolve_movie_manager_credentials", lambda _s, _c: (None, None))

    out = _run(_session(tmp_path), _runtime(watched, output, tmp_path), watched, src, final)

    assert "not configured" in (out["movie_output_folder_skip_reason"] or "")
    assert "left in place" in (out["movie_output_folder_skip_reason"] or "")
    assert out["movie_output_truth_check"] == "skipped"
    assert final.parent.is_dir()
    assert final.exists()


def test_manager_unreachable_refuses_rather_than_assuming_empty(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A failed library fetch is not the same answer as an empty library."""

    watched, output, src, final = _tree(tmp_path)
    monkeypatch.setattr(mod, "resolve_movie_manager_credentials", lambda _s, _c: ("http://127.0.0.1:9", "k"))

    def _boom(*, base_url: str, api_key: str) -> list[dict]:
        msg = "Radarr library fetch failed: could not reach Radarr (connection refused)."
        raise RuntimeError(msg)

    monkeypatch.setattr(mod, "fetch_radarr_library_movies", _boom)

    out = _run(_session(tmp_path), _runtime(watched, output, tmp_path), watched, src, final)

    assert "could not be reached" in (out["movie_output_folder_skip_reason"] or "")
    assert out["movie_output_truth_check"] == "skipped"
    assert final.parent.is_dir()


def test_newest_mtime_returns_none_for_a_tree_with_no_files(tmp_path: Path) -> None:
    empty = tmp_path / "empty"
    (empty / "nested").mkdir(parents=True)
    assert newest_mtime_seconds_under_tree(empty) is None


def test_newest_mtime_ignores_directories_and_takes_the_maximum(tmp_path: Path) -> None:
    root = tmp_path / "tree"
    (root / "a").mkdir(parents=True)
    old = root / "a" / "old.txt"
    new = root / "new.txt"
    old.write_bytes(b"o")
    new.write_bytes(b"n")
    import os

    os.utime(old, (1_000_000, 1_000_000))
    os.utime(new, (2_000_000, 2_000_000))

    assert newest_mtime_seconds_under_tree(root) == pytest.approx(2_000_000, abs=1)


class TestCascadeStopsAtTheOutputRoot:
    """The cascade removes empty parents. It must never step outside the output root."""

    def test_removes_empty_parents_up_to_but_not_including_the_root(self, tmp_path: Path) -> None:
        root = tmp_path / "output"
        deep = root / "Collection" / "Some.Movie.2024"
        deep.mkdir(parents=True)
        deleted: list[str] = []

        _cascade_delete_empty_parents_under_output_root(
            first_parent=deep,
            output_root=root,
            cascade_folders_deleted=deleted,
        )

        assert not deep.exists()
        assert not deep.parent.exists()
        assert root.is_dir(), "the output root itself must never be removed"
        assert len(deleted) == 2

    def test_stops_at_the_first_non_empty_parent(self, tmp_path: Path) -> None:
        root = tmp_path / "output"
        collection = root / "Collection"
        deep = collection / "Some.Movie.2024"
        deep.mkdir(parents=True)
        keeper = collection / "Other.Movie.2020"
        keeper.mkdir()
        deleted: list[str] = []

        _cascade_delete_empty_parents_under_output_root(
            first_parent=deep,
            output_root=root,
            cascade_folders_deleted=deleted,
        )

        assert not deep.exists()
        assert collection.is_dir(), "a parent holding another title must survive"
        assert keeper.is_dir()
        assert deleted == [str(deep.resolve())]

    def test_refuses_a_starting_folder_outside_the_output_root(self, tmp_path: Path) -> None:
        """The guard that stops the walk escaping into unrelated storage."""

        root = tmp_path / "output"
        root.mkdir()
        outside = tmp_path / "somewhere-else" / "nested"
        outside.mkdir(parents=True)
        deleted: list[str] = []

        _cascade_delete_empty_parents_under_output_root(
            first_parent=outside,
            output_root=root,
            cascade_folders_deleted=deleted,
        )

        assert outside.is_dir(), "an empty folder outside the output root must not be removed"
        assert deleted == []

    def test_stops_when_a_parent_has_already_gone(self, tmp_path: Path) -> None:
        root = tmp_path / "output"
        root.mkdir()
        missing = root / "Collection" / "Some.Movie.2024"
        deleted: list[str] = []

        _cascade_delete_empty_parents_under_output_root(
            first_parent=missing,
            output_root=root,
            cascade_folders_deleted=deleted,
        )

        assert deleted == []
        assert root.is_dir()
