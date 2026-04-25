"""Unit tests for Refiner remux pass orchestration (mocked ffprobe)."""

from __future__ import annotations

import os
import time
from dataclasses import replace
from pathlib import Path

import pytest

from mediamop.core.config import MediaMopSettings
from mediamop.modules.refiner import refiner_file_remux_pass_run as runmod
from mediamop.modules.refiner.refiner_path_settings_service import RefinerPathRuntime
from mediamop.modules.refiner.refiner_file_remux_pass_visibility import (
    REMUX_PASS_OUTCOME_FAILED_BEFORE_EXECUTION,
    REMUX_PASS_OUTCOME_FAILED_DURING_EXECUTION,
    REMUX_PASS_OUTCOME_LIVE_SKIPPED_NOT_REQUIRED,
)

from .test_refiner_tv_season_folder_cleanup import _sqlite_session


def _fake_probe() -> dict:
    return {
        "streams": [
            {"index": 0, "codec_type": "video", "codec_name": "h264"},
            {
                "index": 1,
                "codec_type": "audio",
                "codec_name": "aac",
                "channels": 2,
                "tags": {"language": "eng"},
            },
        ],
    }


def _runtime(
    *,
    media: Path,
    home: Path,
    out: Path,
    work_is_default: bool = False,
) -> RefinerPathRuntime:
    work = Path(home).resolve() / "refiner" / "work"
    if not work_is_default:
        work.mkdir(parents=True, exist_ok=True)
    return RefinerPathRuntime(
        watched_folder=str(media.resolve()),
        output_folder=str(out.resolve()),
        work_folder_effective=str(work.resolve()),
        work_folder_is_default=work_is_default,
    )


def test_run_fails_when_watched_root_missing(tmp_path: Path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    settings = replace(MediaMopSettings.load(), mediamop_home=str(home), refiner_watched_folder_min_file_age_seconds=0)
    missing = tmp_path / "nope"
    out = tmp_path / "out"
    out.mkdir()
    rt = _runtime(media=missing, home=home, out=out)
    r = runmod.run_refiner_file_remux_pass(
        settings=settings,
        path_runtime=rt,
        relative_media_path="x.mkv",
    )
    assert r["ok"] is False
    assert r["outcome"] == REMUX_PASS_OUTCOME_FAILED_BEFORE_EXECUTION
    assert r["preflight_status"] == "failed"
    assert "watched folder" in r["reason"].lower()

def test_live_skips_when_no_remux_required_copies_to_output_and_deletes_release_folder(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    home = tmp_path / "home"
    home.mkdir()
    media = tmp_path / "media"
    media.mkdir()
    release = media / "ReleaseTitle"
    release.mkdir()
    mkv = release / "one.mkv"
    mkv.write_bytes(b"x" * 2000)
    out = tmp_path / "out"
    out.mkdir()

    settings = replace(MediaMopSettings.load(), mediamop_home=str(home), refiner_watched_folder_min_file_age_seconds=0)
    rt = _runtime(media=media, home=home, out=out)

    monkeypatch.setattr(runmod, "ffprobe_json", lambda path, mediamop_home, **kwargs: _fake_probe())
    monkeypatch.setattr(runmod, "resolve_ffprobe_ffmpeg", lambda *, mediamop_home: ("ffprobe-x", "ffmpeg-x"))
    monkeypatch.setattr(runmod, "is_remux_required", lambda *_a, **_k: False)

    r = runmod.run_refiner_file_remux_pass(
        settings=settings,
        path_runtime=rt,
        relative_media_path="ReleaseTitle/one.mkv",
    )
    assert r["ok"] is True
    assert r["outcome"] == REMUX_PASS_OUTCOME_LIVE_SKIPPED_NOT_REQUIRED
    assert r["preflight_status"] == "ok"
    assert r.get("live_mutations_skipped") is False
    assert r.get("output_copied_without_remux") is True
    assert Path(r["output_file"]).resolve() == (out / "ReleaseTitle" / "one.mkv").resolve()
    assert (out / "ReleaseTitle" / "one.mkv").read_bytes() == b"x" * 2000
    assert r.get("source_deleted_after_success") is True
    assert r.get("source_folder_deleted") is True
    assert not mkv.exists()
    assert not release.exists()


def test_live_skips_when_no_remux_required_replaces_existing_output_before_cleanup(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    home = tmp_path / "home"
    home.mkdir()
    media = tmp_path / "media"
    media.mkdir()
    release = media / "ReleaseTitle"
    release.mkdir()
    mkv = release / "one.mkv"
    mkv.write_bytes(b"x" * 2000)
    out = tmp_path / "out"
    out.mkdir()
    out_rel = out / "ReleaseTitle"
    out_rel.mkdir()
    existing = out_rel / "one.mkv"
    existing.write_bytes(b"tiny")

    settings = replace(MediaMopSettings.load(), mediamop_home=str(home), refiner_watched_folder_min_file_age_seconds=0)
    rt = _runtime(media=media, home=home, out=out)

    monkeypatch.setattr(runmod, "ffprobe_json", lambda path, mediamop_home, **kwargs: _fake_probe())
    monkeypatch.setattr(runmod, "resolve_ffprobe_ffmpeg", lambda *, mediamop_home: ("ffprobe-x", "ffmpeg-x"))
    monkeypatch.setattr(runmod, "is_remux_required", lambda *_a, **_k: False)

    r = runmod.run_refiner_file_remux_pass(
        settings=settings,
        path_runtime=rt,
        relative_media_path="ReleaseTitle/one.mkv",
    )
    assert r["ok"] is True
    assert r.get("output_replaced_existing") is True
    assert existing.read_bytes() == b"x" * 2000
    assert r.get("source_folder_deleted") is True

def test_live_fails_during_ffmpeg_surfaces_outcome(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    home = tmp_path / "home"
    home.mkdir()
    media = tmp_path / "media"
    media.mkdir()
    mkv = media / "one.mkv"
    mkv.write_bytes(b"x")
    out = tmp_path / "out"
    out.mkdir()

    settings = replace(MediaMopSettings.load(), mediamop_home=str(home), refiner_watched_folder_min_file_age_seconds=0)
    rt = _runtime(media=media, home=home, out=out)

    monkeypatch.setattr(runmod, "ffprobe_json", lambda path, mediamop_home, **kwargs: _fake_probe())
    monkeypatch.setattr(runmod, "resolve_ffprobe_ffmpeg", lambda *, mediamop_home: ("ffprobe-x", "ffmpeg-x"))
    monkeypatch.setattr(runmod, "is_remux_required", lambda *_a, **_k: True)

    def _boom(**_kwargs: object) -> object:
        raise RuntimeError("ffmpeg simulated failure")

    monkeypatch.setattr(runmod, "remux_to_temp_file", _boom)

    r = runmod.run_refiner_file_remux_pass(
        settings=settings,
        path_runtime=rt,
        relative_media_path="one.mkv",
    )
    assert r["ok"] is False
    assert r["outcome"] == REMUX_PASS_OUTCOME_FAILED_DURING_EXECUTION
    assert r["preflight_status"] == "ok"
    assert "ffmpeg simulated failure" in r["reason"]
    assert "plan_summary" in r
    assert mkv.exists()


def test_live_remux_writes_nested_output_and_logs_replacement(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    home = tmp_path / "home"
    home.mkdir()
    media = tmp_path / "media"
    media.mkdir()
    nested = media / "sub" / "d"
    nested.mkdir(parents=True)
    mkv = nested / "deep.mkv"
    mkv.write_bytes(b"x")
    out = tmp_path / "out"
    out.mkdir()
    work = tmp_path / "work"
    work.mkdir()

    settings = replace(MediaMopSettings.load(), mediamop_home=str(home), refiner_watched_folder_min_file_age_seconds=0)
    rt = RefinerPathRuntime(
        watched_folder=str(media.resolve()),
        output_folder=str(out.resolve()),
        work_folder_effective=str(work.resolve()),
        work_folder_is_default=False,
    )

    monkeypatch.setattr(runmod, "ffprobe_json", lambda path, mediamop_home, **kwargs: _fake_probe())
    monkeypatch.setattr(runmod, "resolve_ffprobe_ffmpeg", lambda *, mediamop_home: ("ffprobe-x", "ffmpeg-x"))
    monkeypatch.setattr(runmod, "is_remux_required", lambda *_a, **_k: True)

    tmp_file = work / "t.mkv"
    tmp_file.write_bytes(b"tmp")

    def _fake_remux(**_kwargs: object) -> Path:
        return tmp_file

    monkeypatch.setattr(runmod, "remux_to_temp_file", _fake_remux)

    final = out / "sub" / "d" / "deep.mkv"
    final.parent.mkdir(parents=True, exist_ok=True)
    final.write_bytes(b"old")

    r = runmod.run_refiner_file_remux_pass(
        settings=settings,
        path_runtime=rt,
        relative_media_path="sub/d/deep.mkv",
    )
    assert r["ok"] is True
    assert r.get("output_replaced_existing") is True
    assert "output_replacement_note" in r
    assert Path(r["output_file"]).resolve() == final.resolve()
    assert not mkv.exists()
    assert r.get("source_deleted_after_success") is True
    assert r.get("source_folder_deleted") is True


def test_live_remux_reports_processing_progress(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    home = tmp_path / "home"
    home.mkdir()
    media = tmp_path / "media"
    media.mkdir()
    mkv = media / "movie.mkv"
    mkv.write_bytes(b"x")
    out = tmp_path / "out"
    out.mkdir()
    work = tmp_path / "work"
    work.mkdir()

    settings = replace(MediaMopSettings.load(), mediamop_home=str(home), refiner_watched_folder_min_file_age_seconds=0)
    rt = RefinerPathRuntime(
        watched_folder=str(media.resolve()),
        output_folder=str(out.resolve()),
        work_folder_effective=str(work.resolve()),
        work_folder_is_default=False,
    )

    probe = _fake_probe()
    probe["format"] = {"duration": "100.0"}
    monkeypatch.setattr(runmod, "ffprobe_json", lambda path, mediamop_home, **kwargs: probe)
    monkeypatch.setattr(runmod, "resolve_ffprobe_ffmpeg", lambda *, mediamop_home: ("ffprobe-x", "ffmpeg-x"))
    monkeypatch.setattr(runmod, "is_remux_required", lambda *_a, **_k: True)

    tmp_file = work / "t.mkv"
    tmp_file.write_bytes(b"tmp")
    progress_seen: list[dict[str, object]] = []

    def _fake_remux(**kwargs: object) -> Path:
        cb = kwargs.get("progress_callback")
        assert callable(cb)
        cb({"percent": 25.0, "eta_seconds": 30, "elapsed_seconds": 10, "progress": "continue"})
        return tmp_file

    monkeypatch.setattr(runmod, "remux_to_temp_file", _fake_remux)

    r = runmod.run_refiner_file_remux_pass(
        settings=settings,
        path_runtime=rt,
        relative_media_path="movie.mkv",
        progress_reporter=progress_seen.append,
    )
    assert r["ok"] is True
    assert [item["status"] for item in progress_seen] == ["processing", "processing", "finishing", "finished"]
    assert progress_seen[1]["percent"] == 25.0
    assert progress_seen[-1]["percent"] == 100.0


def test_tv_live_skips_movie_folder_cleanup_deletes_season_folder_when_gates_pass(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, cleanup_session = _sqlite_session(tmp_path)
    home = tmp_path / "home"
    home.mkdir()
    media = tmp_path / "media"
    media.mkdir()
    season = media / "Show" / "S01"
    season.mkdir(parents=True)
    mkv = season / "ep.mkv"
    mkv.write_bytes(b"a" * 400)
    out = tmp_path / "out"
    out.mkdir()
    out_season = out / "Show" / "S01"
    out_season.mkdir(parents=True)
    (out_season / "ep.mkv").write_bytes(b"b" * 80)

    settings = replace(MediaMopSettings.load(), mediamop_home=str(home), refiner_watched_folder_min_file_age_seconds=0)
    rt = _runtime(media=media, home=home, out=out)
    monkeypatch.setattr(runmod, "ffprobe_json", lambda path, mediamop_home, **kwargs: _fake_probe())
    monkeypatch.setattr(runmod, "resolve_ffprobe_ffmpeg", lambda *, mediamop_home: ("ffprobe-x", "ffmpeg-x"))
    monkeypatch.setattr(runmod, "is_remux_required", lambda *_a, **_k: False)
    monkeypatch.setattr(
        "mediamop.modules.refiner.refiner_tv_season_folder_cleanup.fetch_radarr_and_sonarr_queue_rows_for_scan",
        lambda _s, _settings: ([], [], None, None),
    )
    monkeypatch.setattr(
        "mediamop.modules.refiner.refiner_tv_output_cleanup.resolve_sonarr_http_credentials",
        lambda _s, _st: ("http://127.0.0.1:9", "k"),
    )
    monkeypatch.setattr(
        "mediamop.modules.refiner.refiner_tv_output_cleanup.fetch_sonarr_library_episodefiles",
        lambda **kwargs: [],
    )
    old = time.time() - 200_000
    os.utime(mkv, (old, old))
    os.utime(out_season / "ep.mkv", (old, old))

    r = runmod.run_refiner_file_remux_pass(
        settings=settings,
        path_runtime=rt,
        relative_media_path="Show/S01/ep.mkv",
        media_scope="tv",
        cleanup_session=cleanup_session,
        current_job_id=1,
    )
    assert r["ok"] is True
    assert r.get("source_deleted_after_success") is True
    assert r.get("source_folder_deleted") is not True
    assert r.get("tv_season_folder_deleted") is True
    assert r.get("tv_output_season_folder_deleted") is True
    assert "movie_output_folder_deleted" not in r
    assert "movie_output_truth_check" not in r
    assert not mkv.exists()
    assert not season.is_dir()
    assert not (media / "Show").is_dir()
    assert not out_season.is_dir()


def test_movie_live_no_remux_replaces_tiny_existing_output_before_cleanup(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    home = tmp_path / "home"
    home.mkdir()
    media = tmp_path / "media"
    media.mkdir()
    rel = media / "M"
    rel.mkdir()
    mkv = rel / "a.mkv"
    mkv.write_bytes(b"x" * 10_000)
    out = tmp_path / "out"
    out.mkdir()
    out_m = out / "M"
    out_m.mkdir()
    (out_m / "a.mkv").write_bytes(b"tiny")

    settings = replace(MediaMopSettings.load(), mediamop_home=str(home), refiner_watched_folder_min_file_age_seconds=0)
    rt = _runtime(media=media, home=home, out=out)
    monkeypatch.setattr(runmod, "ffprobe_json", lambda path, mediamop_home, **kwargs: _fake_probe())
    monkeypatch.setattr(runmod, "resolve_ffprobe_ffmpeg", lambda *, mediamop_home: ("ffprobe-x", "ffmpeg-x"))
    monkeypatch.setattr(runmod, "is_remux_required", lambda *_a, **_k: False)

    r = runmod.run_refiner_file_remux_pass(
        settings=settings,
        path_runtime=rt,
        relative_media_path="M/a.mkv",
    )
    assert r["ok"] is True
    assert r.get("source_folder_deleted") is True
    assert not mkv.exists()
    assert (out_m / "a.mkv").read_bytes() == b"x" * 10_000
    assert r.get("output_completeness_check") == "passed"
    assert "tv_season_folder_deleted" not in r
    assert "tv_output_season_folder_deleted" not in r
    assert "tv_output_truth_check" not in r


def test_movie_live_skips_when_video_sits_directly_under_watched_root(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    home = tmp_path / "home"
    home.mkdir()
    media = tmp_path / "media"
    media.mkdir()
    mkv = media / "root.mkv"
    mkv.write_bytes(b"x" * 500)
    out = tmp_path / "out"
    out.mkdir()
    (out / "root.mkv").write_bytes(b"y" * 100)

    settings = replace(MediaMopSettings.load(), mediamop_home=str(home), refiner_watched_folder_min_file_age_seconds=0)
    rt = _runtime(media=media, home=home, out=out)
    monkeypatch.setattr(runmod, "ffprobe_json", lambda path, mediamop_home, **kwargs: _fake_probe())
    monkeypatch.setattr(runmod, "resolve_ffprobe_ffmpeg", lambda *, mediamop_home: ("ffprobe-x", "ffmpeg-x"))
    monkeypatch.setattr(runmod, "is_remux_required", lambda *_a, **_k: False)

    r = runmod.run_refiner_file_remux_pass(
        settings=settings,
        path_runtime=rt,
        relative_media_path="root.mkv",
    )
    assert r["ok"] is True
    assert r.get("source_folder_deleted") is False
    assert mkv.exists()


def test_movie_live_folder_delete_skips_when_rmtree_raises(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    home = tmp_path / "home"
    home.mkdir()
    media = tmp_path / "media"
    media.mkdir()
    rel = media / "X"
    rel.mkdir()
    mkv = rel / "a.mkv"
    mkv.write_bytes(b"x" * 600)
    out = tmp_path / "out"
    out.mkdir()
    out_x = out / "X"
    out_x.mkdir()
    (out_x / "a.mkv").write_bytes(b"y" * 120)

    settings = replace(MediaMopSettings.load(), mediamop_home=str(home), refiner_watched_folder_min_file_age_seconds=0)
    rt = _runtime(media=media, home=home, out=out)
    monkeypatch.setattr(runmod, "ffprobe_json", lambda path, mediamop_home, **kwargs: _fake_probe())
    monkeypatch.setattr(runmod, "resolve_ffprobe_ffmpeg", lambda *, mediamop_home: ("ffprobe-x", "ffmpeg-x"))
    monkeypatch.setattr(runmod, "is_remux_required", lambda *_a, **_k: False)

    def _boom(path: str | Path, *a: object, **k: object) -> None:
        raise PermissionError(13, "locked", str(path))

    monkeypatch.setattr(runmod.shutil, "rmtree", _boom)

    r = runmod.run_refiner_file_remux_pass(
        settings=settings,
        path_runtime=rt,
        relative_media_path="X/a.mkv",
    )
    assert r["ok"] is True
    assert r.get("source_folder_deleted") is False
    assert mkv.exists()


def test_source_file_outside_watched_root_fails_relative_to_guard(tmp_path: Path) -> None:
    watched = tmp_path / "w_root"
    watched.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    f = outside / "x.mkv"
    f.write_bytes(b"1")
    with pytest.raises(ValueError):
        f.resolve().relative_to(watched.resolve())


def test_preflight_failure_contract_has_no_cleanup_mutations(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    home = tmp_path / "home"
    home.mkdir()
    media = tmp_path / "media"
    media.mkdir()
    src = media / "bad.mkv"
    src.write_bytes(b"x" * 100)
    out = tmp_path / "out"
    out.mkdir()
    settings = replace(MediaMopSettings.load(), mediamop_home=str(home), refiner_watched_folder_min_file_age_seconds=0)
    rt = _runtime(media=media, home=home, out=out)

    def _probe_boom(path: Path, mediamop_home: str, **_kwargs: object) -> dict:
        raise RuntimeError("probe failure")

    monkeypatch.setattr(runmod, "ffprobe_json", _probe_boom)
    r = runmod.run_refiner_file_remux_pass(
        settings=settings,
        path_runtime=rt,
        relative_media_path="bad.mkv",
    )
    assert r["ok"] is False
    assert r["outcome"] == REMUX_PASS_OUTCOME_FAILED_BEFORE_EXECUTION
    assert r["preflight_status"] == "failed"
    assert "probe failure" in r["preflight_reason"]
    assert "source_deleted_after_success" not in r
    assert "source_folder_deleted" not in r
    assert "movie_output_folder_deleted" not in r
    assert "tv_output_season_folder_deleted" not in r
    assert "output_file" not in r
    assert "ffmpeg_argv" not in r


def test_preflight_failure_contract_for_age_gate_has_no_cleanup_mutations(tmp_path: Path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    media = tmp_path / "media"
    media.mkdir()
    src = media / "young.mkv"
    src.write_bytes(b"x" * 200)
    out = tmp_path / "out"
    out.mkdir()
    settings = replace(MediaMopSettings.load(), mediamop_home=str(home), refiner_watched_folder_min_file_age_seconds=999_999)
    rt = _runtime(media=media, home=home, out=out)

    r = runmod.run_refiner_file_remux_pass(
        settings=settings,
        path_runtime=rt,
        relative_media_path="young.mkv",
    )
    assert r["ok"] is False
    assert r["outcome"] == REMUX_PASS_OUTCOME_FAILED_BEFORE_EXECUTION
    assert r["preflight_status"] == "failed"
    assert "too recently" in r["preflight_reason"]
    assert "source_deleted_after_success" not in r
    assert "source_folder_deleted" not in r
    assert "movie_output_folder_deleted" not in r
    assert "tv_output_season_folder_deleted" not in r


def test_default_work_dir_created_when_flag_set(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    home = tmp_path / "home"
    home.mkdir()
    media = tmp_path / "media"
    media.mkdir()
    rel = media / "R"
    rel.mkdir()
    mkv = rel / "one.mkv"
    mkv.write_bytes(b"x" * 800)
    out = tmp_path / "out"
    out.mkdir()
    out_r = out / "R"
    out_r.mkdir()
    (out_r / "one.mkv").write_bytes(b"z" * 100)

    settings = replace(MediaMopSettings.load(), mediamop_home=str(home), refiner_watched_folder_min_file_age_seconds=0)
    work_default = Path(home).resolve() / "refiner" / "work"
    rt = RefinerPathRuntime(
        watched_folder=str(media.resolve()),
        output_folder=str(out.resolve()),
        work_folder_effective=str(work_default),
        work_folder_is_default=True,
    )

    monkeypatch.setattr(runmod, "ffprobe_json", lambda path, mediamop_home, **kwargs: _fake_probe())
    monkeypatch.setattr(runmod, "resolve_ffprobe_ffmpeg", lambda *, mediamop_home: ("ffprobe-x", "ffmpeg-x"))
    monkeypatch.setattr(runmod, "is_remux_required", lambda *_a, **_k: True)

    tmp_file = work_default / "t.mkv"

    def _fake_remux(*, work_dir: Path, **_kwargs: object) -> Path:
        work_dir.mkdir(parents=True, exist_ok=True)
        tmp_file.write_bytes(b"t" * 200)
        return tmp_file

    monkeypatch.setattr(runmod, "remux_to_temp_file", _fake_remux)

    r = runmod.run_refiner_file_remux_pass(
        settings=settings,
        path_runtime=rt,
        relative_media_path="R/one.mkv",
    )
    assert r["ok"] is True
    assert work_default.is_dir()
    assert r.get("source_folder_deleted") is True
    assert not mkv.exists()


