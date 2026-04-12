"""Unit tests for Refiner remux pass orchestration (mocked ffprobe)."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from mediamop.core.config import MediaMopSettings
from mediamop.modules.refiner import refiner_file_remux_pass_run as runmod
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


def test_run_fails_without_media_root(tmp_path: Path) -> None:
    settings = replace(
        MediaMopSettings.load(),
        mediamop_home=str(tmp_path / "home"),
        refiner_remux_media_root=None,
    )
    r = runmod.run_refiner_file_remux_pass(
        settings=settings,
        relative_media_path="x.mkv",
        dry_run=True,
    )
    assert r["ok"] is False
    assert r["outcome"] == REMUX_PASS_OUTCOME_FAILED_BEFORE_EXECUTION
    assert "MEDIAMOP_REFINER_REMUX_MEDIA_ROOT" in r["reason"]


def test_dry_run_uses_ffprobe_and_returns_plan_lines(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    home = tmp_path / "home"
    home.mkdir()
    media = tmp_path / "media"
    media.mkdir()
    mkv = media / "one.mkv"
    mkv.write_bytes(b"not-a-real-mkv")

    settings = replace(
        MediaMopSettings.load(),
        mediamop_home=str(home),
        refiner_remux_media_root=str(media),
    )

    monkeypatch.setattr(runmod, "ffprobe_json", lambda path, mediamop_home: _fake_probe())
    monkeypatch.setattr(runmod, "resolve_ffprobe_ffmpeg", lambda *, mediamop_home: ("ffprobe-x", "ffmpeg-x"))

    r = runmod.run_refiner_file_remux_pass(
        settings=settings,
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


def test_live_skips_when_no_remux_required(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    home = tmp_path / "home"
    home.mkdir()
    media = tmp_path / "media"
    media.mkdir()
    mkv = media / "one.mkv"
    mkv.write_bytes(b"x")

    settings = replace(
        MediaMopSettings.load(),
        mediamop_home=str(home),
        refiner_remux_media_root=str(media),
    )

    monkeypatch.setattr(runmod, "ffprobe_json", lambda path, mediamop_home: _fake_probe())
    monkeypatch.setattr(runmod, "resolve_ffprobe_ffmpeg", lambda *, mediamop_home: ("ffprobe-x", "ffmpeg-x"))
    monkeypatch.setattr(runmod, "is_remux_required", lambda *_a, **_k: False)

    r = runmod.run_refiner_file_remux_pass(
        settings=settings,
        relative_media_path="one.mkv",
        dry_run=False,
    )
    assert r["ok"] is True
    assert r["outcome"] == REMUX_PASS_OUTCOME_LIVE_SKIPPED_NOT_REQUIRED
    assert r.get("live_mutations_skipped") is True


def test_live_fails_during_ffmpeg_surfaces_outcome(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    home = tmp_path / "home"
    home.mkdir()
    media = tmp_path / "media"
    media.mkdir()
    mkv = media / "one.mkv"
    mkv.write_bytes(b"x")

    settings = replace(
        MediaMopSettings.load(),
        mediamop_home=str(home),
        refiner_remux_media_root=str(media),
    )

    monkeypatch.setattr(runmod, "ffprobe_json", lambda path, mediamop_home: _fake_probe())
    monkeypatch.setattr(runmod, "resolve_ffprobe_ffmpeg", lambda *, mediamop_home: ("ffprobe-x", "ffmpeg-x"))
    monkeypatch.setattr(runmod, "is_remux_required", lambda *_a, **_k: True)

    def _boom(**_kwargs: object) -> object:
        raise RuntimeError("ffmpeg simulated failure")

    monkeypatch.setattr(runmod, "remux_to_temp_file", _boom)

    r = runmod.run_refiner_file_remux_pass(
        settings=settings,
        relative_media_path="one.mkv",
        dry_run=False,
    )
    assert r["ok"] is False
    assert r["outcome"] == REMUX_PASS_OUTCOME_FAILED_DURING_EXECUTION
    assert "ffmpeg simulated failure" in r["reason"]
    assert "plan_summary" in r
