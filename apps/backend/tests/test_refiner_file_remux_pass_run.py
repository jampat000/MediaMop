"""Unit tests for Refiner remux pass orchestration (mocked ffprobe)."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from mediamop.core.config import MediaMopSettings
from mediamop.modules.refiner import refiner_file_remux_pass_run as runmod
from mediamop.modules.refiner.refiner_path_settings_service import RefinerPathRuntime
from mediamop.modules.refiner.refiner_file_remux_pass_visibility import (
    REMUX_PASS_OUTCOME_DRY_RUN_PLANNED,
    REMUX_PASS_OUTCOME_FAILED_BEFORE_EXECUTION,
    REMUX_PASS_OUTCOME_FAILED_DURING_EXECUTION,
    REMUX_PASS_OUTCOME_LIVE_SKIPPED_NOT_REQUIRED,
)


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
    dry: bool,
    out: Path | None = None,
    work_is_default: bool = False,
) -> RefinerPathRuntime:
    work = Path(home).resolve() / "refiner" / "work"
    if not work_is_default:
        work.mkdir(parents=True, exist_ok=True)
    if dry:
        out_s = ""
    else:
        assert out is not None
        out_s = str(out.resolve())
    return RefinerPathRuntime(
        watched_folder=str(media.resolve()),
        output_folder=out_s,
        work_folder_effective=str(work.resolve()),
        work_folder_is_default=work_is_default,
    )


def test_run_fails_when_watched_root_missing(tmp_path: Path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    settings = replace(MediaMopSettings.load(), mediamop_home=str(home), refiner_watched_folder_min_file_age_seconds=0)
    missing = tmp_path / "nope"
    rt = _runtime(media=missing, home=home, dry=True)
    r = runmod.run_refiner_file_remux_pass(
        settings=settings,
        path_runtime=rt,
        relative_media_path="x.mkv",
        dry_run=True,
    )
    assert r["ok"] is False
    assert r["outcome"] == REMUX_PASS_OUTCOME_FAILED_BEFORE_EXECUTION
    assert "watched folder" in r["reason"].lower()


def test_dry_run_uses_ffprobe_and_returns_plan_lines(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    home = tmp_path / "home"
    home.mkdir()
    media = tmp_path / "media"
    media.mkdir()
    mkv = media / "one.mkv"
    mkv.write_bytes(b"not-a-real-mkv")

    settings = replace(MediaMopSettings.load(), mediamop_home=str(home), refiner_watched_folder_min_file_age_seconds=0)
    rt = _runtime(media=media, home=home, dry=True)

    monkeypatch.setattr(runmod, "ffprobe_json", lambda path, mediamop_home: _fake_probe())
    monkeypatch.setattr(runmod, "resolve_ffprobe_ffmpeg", lambda *, mediamop_home: ("ffprobe-x", "ffmpeg-x"))

    r = runmod.run_refiner_file_remux_pass(
        settings=settings,
        path_runtime=rt,
        relative_media_path="one.mkv",
        dry_run=True,
    )
    assert r["ok"] is True
    assert r["dry_run"] is True
    assert r["outcome"] == REMUX_PASS_OUTCOME_DRY_RUN_PLANNED
    assert "inspected_source_path" in r
    assert "plan_summary" in r
    assert "audio_before" in r
    assert "audio_after" in r
    assert isinstance(r.get("ffmpeg_argv"), list)
    assert len(r["ffmpeg_argv"]) > 3
    assert mkv.exists()


def test_live_skips_when_no_remux_required_deletes_source(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    home = tmp_path / "home"
    home.mkdir()
    media = tmp_path / "media"
    media.mkdir()
    mkv = media / "one.mkv"
    mkv.write_bytes(b"x")
    out = tmp_path / "out"
    out.mkdir()

    settings = replace(MediaMopSettings.load(), mediamop_home=str(home), refiner_watched_folder_min_file_age_seconds=0)
    rt = _runtime(media=media, home=home, dry=False, out=out)

    monkeypatch.setattr(runmod, "ffprobe_json", lambda path, mediamop_home: _fake_probe())
    monkeypatch.setattr(runmod, "resolve_ffprobe_ffmpeg", lambda *, mediamop_home: ("ffprobe-x", "ffmpeg-x"))
    monkeypatch.setattr(runmod, "is_remux_required", lambda *_a, **_k: False)

    r = runmod.run_refiner_file_remux_pass(
        settings=settings,
        path_runtime=rt,
        relative_media_path="one.mkv",
        dry_run=False,
    )
    assert r["ok"] is True
    assert r["outcome"] == REMUX_PASS_OUTCOME_LIVE_SKIPPED_NOT_REQUIRED
    assert r.get("live_mutations_skipped") is True
    assert r.get("source_deleted_after_success") is True
    assert not mkv.exists()


def test_dry_run_does_not_delete_source(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    home = tmp_path / "home"
    home.mkdir()
    media = tmp_path / "media"
    media.mkdir()
    mkv = media / "one.mkv"
    mkv.write_bytes(b"x")

    settings = replace(MediaMopSettings.load(), mediamop_home=str(home), refiner_watched_folder_min_file_age_seconds=0)
    rt = _runtime(media=media, home=home, dry=True)

    monkeypatch.setattr(runmod, "ffprobe_json", lambda path, mediamop_home: _fake_probe())
    monkeypatch.setattr(runmod, "resolve_ffprobe_ffmpeg", lambda *, mediamop_home: ("ffprobe-x", "ffmpeg-x"))
    monkeypatch.setattr(runmod, "is_remux_required", lambda *_a, **_k: False)

    r = runmod.run_refiner_file_remux_pass(
        settings=settings,
        path_runtime=rt,
        relative_media_path="one.mkv",
        dry_run=True,
    )
    assert r["ok"] is True
    assert mkv.exists()
    assert "source_deleted_after_success" not in r


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
    rt = _runtime(media=media, home=home, dry=False, out=out)

    monkeypatch.setattr(runmod, "ffprobe_json", lambda path, mediamop_home: _fake_probe())
    monkeypatch.setattr(runmod, "resolve_ffprobe_ffmpeg", lambda *, mediamop_home: ("ffprobe-x", "ffmpeg-x"))
    monkeypatch.setattr(runmod, "is_remux_required", lambda *_a, **_k: True)

    def _boom(**_kwargs: object) -> object:
        raise RuntimeError("ffmpeg simulated failure")

    monkeypatch.setattr(runmod, "remux_to_temp_file", _boom)

    r = runmod.run_refiner_file_remux_pass(
        settings=settings,
        path_runtime=rt,
        relative_media_path="one.mkv",
        dry_run=False,
    )
    assert r["ok"] is False
    assert r["outcome"] == REMUX_PASS_OUTCOME_FAILED_DURING_EXECUTION
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

    monkeypatch.setattr(runmod, "ffprobe_json", lambda path, mediamop_home: _fake_probe())
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
        dry_run=False,
    )
    assert r["ok"] is True
    assert r.get("output_replaced_existing") is True
    assert "output_replacement_note" in r
    assert Path(r["output_file"]).resolve() == final.resolve()
    assert not mkv.exists()
    assert r.get("source_deleted_after_success") is True


def test_source_file_not_eligible_for_delete_outside_watched_root(tmp_path: Path) -> None:
    watched = tmp_path / "w_root"
    watched.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    f = outside / "x.mkv"
    f.write_bytes(b"1")
    assert not runmod._source_file_eligible_for_automatic_delete(src=f, watched_root=watched.resolve())


def test_default_work_dir_created_when_flag_set(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    home = tmp_path / "home"
    home.mkdir()
    media = tmp_path / "media"
    media.mkdir()
    mkv = media / "one.mkv"
    mkv.write_bytes(b"x")
    out = tmp_path / "out"
    out.mkdir()

    settings = replace(MediaMopSettings.load(), mediamop_home=str(home), refiner_watched_folder_min_file_age_seconds=0)
    work_default = Path(home).resolve() / "refiner" / "work"
    rt = RefinerPathRuntime(
        watched_folder=str(media.resolve()),
        output_folder=str(out.resolve()),
        work_folder_effective=str(work_default),
        work_folder_is_default=True,
    )

    monkeypatch.setattr(runmod, "ffprobe_json", lambda path, mediamop_home: _fake_probe())
    monkeypatch.setattr(runmod, "resolve_ffprobe_ffmpeg", lambda *, mediamop_home: ("ffprobe-x", "ffmpeg-x"))
    monkeypatch.setattr(runmod, "is_remux_required", lambda *_a, **_k: True)

    tmp_file = work_default / "t.mkv"

    def _fake_remux(*, work_dir: Path, **_kwargs: object) -> Path:
        work_dir.mkdir(parents=True, exist_ok=True)
        tmp_file.write_bytes(b"t")
        return tmp_file

    monkeypatch.setattr(runmod, "remux_to_temp_file", _fake_remux)

    r = runmod.run_refiner_file_remux_pass(
        settings=settings,
        path_runtime=rt,
        relative_media_path="one.mkv",
        dry_run=False,
    )
    assert r["ok"] is True
    assert work_default.is_dir()
