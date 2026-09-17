"""The one scenario that runs the real ffprobe and ffmpeg, on a two-second file generated here.

Skipped when ffmpeg and ffprobe are not on PATH (or ``WEIR_CONTRACT_REAL_FFMPEG_DIR``). The fake tools
prove the orchestration; this proves the argv Weir builds is one real ffmpeg accepts.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from tests.contract.processing import _helpers as h

pytestmark = pytest.mark.real_ffmpeg


def _tool(env: dict[str, str], name: str) -> str:
    folder = Path(env["WEIR_FFMPEG_DIR"])
    for candidate in (folder / f"{name}.exe", folder / name):
        if candidate.is_file():
            return str(candidate)
    raise AssertionError(f"{name} not found in {folder}")


def _audio_languages(ffprobe: str, path: Path) -> list[str]:
    result = subprocess.run(
        [ffprobe, "-v", "error", "-print_format", "json", "-show_streams", str(path)],
        capture_output=True,
        text=True,
        check=True,
    )
    streams = json.loads(result.stdout)["streams"]
    return [(s.get("tags") or {}).get("language", "") for s in streams if s.get("codec_type") == "audio"]


def test_real_ffmpeg_remuxes_a_handed_off_file_and_drops_the_unwanted_language(
    server_factory, client_factory, fake_managers, real_ffmpeg_env, tmp_path: Path
) -> None:
    folders = h.Folders.make(tmp_path)
    release = folders.watched / "Tiny.Real.Film.2024"
    release.mkdir()
    source = release / "tiny.mkv"
    ffmpeg = _tool(real_ffmpeg_env, "ffmpeg")
    ffprobe = _tool(real_ffmpeg_env, "ffprobe")
    subprocess.run(
        [
            ffmpeg,
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "testsrc=duration=2:size=64x64:rate=10",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:duration=2",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=880:duration=2",
            "-map",
            "0:v",
            "-map",
            "1:a",
            "-map",
            "2:a",
            "-c:v",
            "mpeg4",
            "-c:a",
            "mp2",
            "-metadata:s:a:0",
            "language=eng",
            "-metadata:s:a:1",
            "language=fre",
            str(source),
        ],
        check=True,
        capture_output=True,
    )
    assert _audio_languages(ffprobe, source) == ["eng", "fre"]

    server = server_factory(
        env={
            **real_ffmpeg_env,
            "WEIR_REFINER_WORKER_COUNT": "1",
            "WEIR_MEDIA_MANAGER_WEBHOOK_SECRET": h.WEBHOOK_SECRET,
        }
    )
    admin = client_factory(server)
    admin.ensure_admin()
    fake, _library = h.deluno_setup(admin, fake_managers, folders)

    h.post_handoff(admin, handoff_id="handoff-real-1", source_path=source)
    h.wait_for_handoff_state(admin, "handoff-real-1", "completed", timeout_s=120)

    output = folders.output / "Tiny.Real.Film.2024" / "tiny.mkv"
    assert output.is_file()
    assert _audio_languages(ffprobe, output) == ["eng"]
    assert [r["status"] for r in h.callbacks(fake, "handoff-real-1")] == ["completed"]
