"""Refusal-to-delete guards on Refiner Pass 3b (TV season output-folder cleanup).

The TV path removes a whole **season** folder from the operator's library, so it has more
to lose than the Movies equivalent and correspondingly more gates. This file covers the
reachable refusals that were untested, and the cascade walk that must stop at the output
root.

Mirrors ``test_refiner_movie_output_cleanup_guards.py``. Every test asserts the season
folder still exists, not merely that a reason was written: a gate that reports a reason
and deletes anyway would pass the weaker assertion.
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
from mediamop.modules.refiner import refiner_tv_output_cleanup as mod
from mediamop.modules.refiner.refiner_path_settings_service import RefinerPathRuntime
from mediamop.modules.refiner.refiner_tv_output_cleanup import (
    _cascade_delete_empty_parents_under_tv_output_root,
    maybe_run_tv_output_season_folder_cleanup_after_remux,
)


def _session(tmp_path: Path) -> Session:
    engine = create_engine(
        f"sqlite:///{tmp_path / 'tvguards.sqlite'}",
        connect_args={"check_same_thread": False},
        future=True,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, class_=Session, autoflush=False, autocommit=False, future=True)()


def _settings(*, min_out_age: int = 0) -> MediaMopSettings:
    return replace(MediaMopSettings.load(), refiner_tv_output_cleanup_min_age_seconds=min_out_age)


def _tree(tmp_path: Path) -> tuple[Path, Path, Path, Path]:
    """watched/, output/, the source episode, and the written output episode."""

    watched = tmp_path / "watched"
    output = tmp_path / "output"
    (watched / "Some.Show" / "Season 01").mkdir(parents=True)
    (output / "Some.Show" / "Season 01").mkdir(parents=True)
    src = watched / "Some.Show" / "Season 01" / "s01e01.mkv"
    src.write_bytes(b"source")
    final = output / "Some.Show" / "Season 01" / "s01e01.mkv"
    final.write_bytes(b"output")
    return watched, output, src, final


def _runtime(watched: Path, output: Path, tmp_path: Path) -> RefinerPathRuntime:
    return RefinerPathRuntime(
        watched_folder=str(watched),
        output_folder=str(output),
        work_folder_effective=str(tmp_path / "work"),
        work_folder_is_default=True,
    )


def _run(session: Session | None, rt: RefinerPathRuntime, watched: Path, src: Path, final: Path | None) -> dict:
    out: dict = {}
    maybe_run_tv_output_season_folder_cleanup_after_remux(
        session=session,
        settings=_settings(),
        path_runtime=rt,
        watched_root=watched,
        src=src,
        final_output_file=final,
        relative_media_path="Some.Show/Season 01/s01e01.mkv",
        current_job_id=1,
        media_scope="tv",
        out=out,
    )
    return out


def _reason(out: dict) -> str:
    return out.get("tv_output_season_folder_skip_reason") or ""


def test_movie_scope_is_refused_by_the_tv_path(tmp_path: Path) -> None:
    watched, output, src, final = _tree(tmp_path)
    out: dict = {}
    maybe_run_tv_output_season_folder_cleanup_after_remux(
        session=_session(tmp_path),
        settings=_settings(),
        path_runtime=_runtime(watched, output, tmp_path),
        watched_root=watched,
        src=src,
        final_output_file=final,
        relative_media_path="Some.Show/Season 01/s01e01.mkv",
        current_job_id=1,
        media_scope="movie",
        out=out,
    )

    assert "applies only to TV" in _reason(out)
    assert final.parent.is_dir()


def test_no_database_session_refuses(tmp_path: Path) -> None:
    watched, output, src, final = _tree(tmp_path)
    out = _run(None, _runtime(watched, output, tmp_path), watched, src, final)

    assert _reason(out)
    assert out["tv_output_truth_check"] == "skipped"
    assert final.parent.is_dir(), "the season folder must survive a refusal"


def test_output_folder_missing_on_disk_refuses(tmp_path: Path) -> None:
    watched, output, src, final = _tree(tmp_path)
    rt = replace(_runtime(watched, output, tmp_path), output_folder=str(tmp_path / "nope"))
    out = _run(_session(tmp_path), rt, watched, src, final)

    assert "missing on disk" in _reason(out)
    assert final.parent.is_dir()


def test_source_outside_the_watched_folder_refuses(tmp_path: Path) -> None:
    watched, output, _src, final = _tree(tmp_path)
    stray = tmp_path / "elsewhere" / "s01e01.mkv"
    stray.parent.mkdir(parents=True)
    stray.write_bytes(b"x")

    out = _run(_session(tmp_path), _runtime(watched, output, tmp_path), watched, stray, final)

    assert "watched folder" in _reason(out)
    assert final.parent.is_dir()
    assert stray.exists()


def test_season_folder_with_no_episode_media_refuses(tmp_path: Path) -> None:
    """Without a direct-child episode there is no age to gate on, so nothing is removed."""

    watched, output, src, final = _tree(tmp_path)
    final.unlink()
    (final.parent / "readme.txt").write_bytes(b"not media")

    out = _run(_session(tmp_path), _runtime(watched, output, tmp_path), watched, src, final)

    assert "did not find any supported episode media file" in _reason(out)
    assert out["tv_output_truth_check"] == "skipped"
    assert final.parent.is_dir()


def test_missing_manager_credentials_leave_the_season_in_place(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No credentials means no library truth, and no library truth means no deletion."""

    watched, output, src, final = _tree(tmp_path)
    monkeypatch.setattr(mod, "resolve_tv_manager_credentials", lambda _s, _c: (None, None))

    out = _run(_session(tmp_path), _runtime(watched, output, tmp_path), watched, src, final)

    assert "not configured" in _reason(out)
    assert "left in place" in _reason(out)
    assert out["tv_output_truth_check"] == "skipped"
    assert final.parent.is_dir()
    assert final.exists()


def test_manager_unreachable_refuses_rather_than_assuming_empty(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A failed episode-file fetch is not the same answer as an empty library."""

    watched, output, src, final = _tree(tmp_path)
    monkeypatch.setattr(mod, "resolve_tv_manager_credentials", lambda _s, _c: ("http://127.0.0.1:9", "k"))

    def _boom(*, base_url: str, api_key: str) -> list[dict]:
        msg = "Sonarr library fetch failed: could not reach Sonarr (connection refused)."
        raise RuntimeError(msg)

    monkeypatch.setattr(mod, "fetch_sonarr_library_episodefiles", _boom)

    out = _run(_session(tmp_path), _runtime(watched, output, tmp_path), watched, src, final)

    assert "could not be reached" in _reason(out)
    assert out["tv_output_truth_check"] == "skipped"
    assert final.parent.is_dir()


class TestTvCascadeStopsAtTheOutputRoot:
    """Removing an empty season folder may cascade to the show folder, never past the root."""

    def test_removes_empty_show_folder_but_never_the_root(self, tmp_path: Path) -> None:
        root = tmp_path / "output"
        season = root / "Some.Show" / "Season 01"
        season.mkdir(parents=True)
        deleted: list[str] = []

        _cascade_delete_empty_parents_under_tv_output_root(
            first_parent=season,
            output_root=root,
            cascade_folders_deleted=deleted,
        )

        assert not season.exists()
        assert not season.parent.exists(), "an empty show folder should go with its last season"
        assert root.is_dir(), "the output root itself must never be removed"
        assert len(deleted) == 2

    def test_keeps_a_show_folder_that_still_has_another_season(self, tmp_path: Path) -> None:
        root = tmp_path / "output"
        show = root / "Some.Show"
        season1 = show / "Season 01"
        season2 = show / "Season 02"
        season1.mkdir(parents=True)
        season2.mkdir()
        deleted: list[str] = []

        _cascade_delete_empty_parents_under_tv_output_root(
            first_parent=season1,
            output_root=root,
            cascade_folders_deleted=deleted,
        )

        assert not season1.exists()
        assert show.is_dir(), "a show with another season must survive"
        assert season2.is_dir()
        assert deleted == [str(season1.resolve())]

    def test_refuses_a_starting_folder_outside_the_output_root(self, tmp_path: Path) -> None:
        root = tmp_path / "output"
        root.mkdir()
        outside = tmp_path / "somewhere-else" / "Season 01"
        outside.mkdir(parents=True)
        deleted: list[str] = []

        _cascade_delete_empty_parents_under_tv_output_root(
            first_parent=outside,
            output_root=root,
            cascade_folders_deleted=deleted,
        )

        assert outside.is_dir(), "an empty folder outside the output root must not be removed"
        assert deleted == []
