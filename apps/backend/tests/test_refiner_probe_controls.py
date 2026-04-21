from __future__ import annotations

from pathlib import Path

import pytest

from mediamop.core.config import MediaMopSettings
from mediamop.modules.refiner.refiner_remux_mux import build_ffprobe_argv


def test_build_ffprobe_argv_includes_probe_controls() -> None:
    argv = build_ffprobe_argv(
        ffprobe_bin="ffprobe-x",
        src=Path("/tmp/sample.mkv"),
        probe_size_mb=25,
        analyze_duration_seconds=14,
    )
    assert "-probesize" in argv
    assert "-analyzeduration" in argv
    assert argv[argv.index("-probesize") + 1] == str(25 * 1024 * 1024)
    assert argv[argv.index("-analyzeduration") + 1] == str(14 * 1_000_000)


def test_build_ffprobe_argv_clamps_out_of_range_controls() -> None:
    argv = build_ffprobe_argv(
        ffprobe_bin="ffprobe-x",
        src=Path("/tmp/sample.mkv"),
        probe_size_mb=9999,
        analyze_duration_seconds=0,
    )
    assert argv[argv.index("-probesize") + 1] == str(1024 * 1024 * 1024)
    assert argv[argv.index("-analyzeduration") + 1] == str(1 * 1_000_000)


def test_refiner_probe_controls_load_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MEDIAMOP_REFINER_PROBE_SIZE_MB", "32")
    monkeypatch.setenv("MEDIAMOP_REFINER_ANALYZE_DURATION_SECONDS", "28")
    s = MediaMopSettings.load()
    assert s.refiner_probe_size_mb == 32
    assert s.refiner_analyze_duration_seconds == 28

