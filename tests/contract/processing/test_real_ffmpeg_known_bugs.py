"""Real-ffmpeg proof for #539 items 1 and 3, and #494: bugs that only show up against real ffmpeg.

The fake ffmpeg tool cannot reproduce these: it lets a scenario hand a classification straight to
Weir (``probe_error=...``), so it never exercises the actual bug, which is in how Weir reads
ffprobe's own stderr. Empirically checked against the bundled ffmpeg
(``dist/windows/MediaMopServer/_internal/bin/ffmpeg``) while writing these tests:

- ``ffprobe_json`` (``refiner_remux_mux.py``) runs ffprobe with ``-v quiet``. On a zero-filled
  ``.mkv``, real ffprobe exits 1 with **empty stderr** and stdout ``{\\n\\n}`` — the classification
  markers Weir looks for (``EBML header parsing failed``, etc.) never reach it with ``-v quiet``;
  they are present with ``-v error``. So ``MediaUnreadableError`` can never fire on a real unreadable
  file, and neither can the reject-policy path that depends on it (#539 item 1, #494). Fixed on dotnet:
  ffprobe runs with ``-v error`` (``FfmpegCommands.BuildFfprobeArgv``, #522 part 2) and the reject job
  handler (``RefinerRejectHandler``, #522 part 4) reports the hand-off ``failed`` with
  ``disposition: rejected`` end to end. The Python backend is being retired (ADR-0017) and keeps the bug.
- ``validate_media_integrity`` runs the primary video through ``ffmpeg ... -f null -`` and only
  fails on a non-zero exit code. On a real MKV truncated after encoding, ffmpeg prints
  ``File ended prematurely`` to stderr but still **exits 0**, and the container's own header still
  reports the original (pre-truncation) duration — so this check does not catch it, and Weir accepts
  the file as complete (#539 item 3). It is also skipped outright on Windows
  (``if os.name != "nt":`` in ``file_remux_pass/run.py``), which is item 5's Windows question, not
  fixed by this test.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from tests.contract.processing import _helpers as h
from tests.contract.support.client import API

pytestmark = pytest.mark.real_ffmpeg


def _tool(env: dict[str, str], name: str) -> str:
    folder = Path(env["WEIR_FFMPEG_DIR"])
    for candidate in (folder / f"{name}.exe", folder / name):
        if candidate.is_file():
            return str(candidate)
    raise AssertionError(f"{name} not found in {folder}")


@pytest.mark.known_bug(issue=539, backends=("python",))
@pytest.mark.known_bug(issue=494, backends=("python",))
def test_unreadable_zero_filled_media_is_classified_unreadable_and_rejected(
    server_factory, client_factory, fake_managers, real_ffmpeg_env, tmp_path: Path
) -> None:
    folders = h.Folders.make(tmp_path)
    release = folders.watched / "Zero.Filled.494"
    release.mkdir()
    source = release / "film.mkv"
    # All zero bytes, like the 10GB file from #494 (`fsutil file createnew`) but small enough for a
    # contract test: real ffprobe reports the same "EBML header parsing failed" either way.
    source.write_bytes(b"\x00" * (2 * 1024 * 1024))

    server = server_factory(
        env={
            **real_ffmpeg_env,
            "WEIR_REFINER_WORKER_COUNT": "1",
            "WEIR_MEDIA_MANAGER_WEBHOOK_SECRET": h.WEBHOOK_SECRET,
        }
    )
    admin = client_factory(server)
    admin.ensure_admin()
    fake, library = h.deluno_setup(
        admin, fake_managers, folders, capabilities=["processor-reject-regrab"], failure_policy="reject"
    )

    h.post_handoff(admin, handoff_id="handoff-zero-494", source_path=source)
    h.wait_for_handoff_state(admin, "handoff-zero-494", "rejected", timeout_s=90)

    reports = h.callbacks(fake, "handoff-zero-494")
    assert reports, "the rejection must be reported to the manager"
    report = reports[-1]
    assert report["status"] == "failed"
    assert report["disposition"] == "rejected"
    assert not report.get("outputPath"), (
        "an unreadable file must never be reported completed with a copy of itself as output (#494)"
    )

    # GET /refiner/files must not 500 after this (#494 item 3 / #530), and must show the rejection.
    files_response = admin.get(f"{API}/refiner/files")
    assert files_response.status_code == 200, files_response.text
    row = h.file_row(admin, library["id"], "Zero.Filled.494/film.mkv")
    assert row is not None, "the rejection must leave a Files row behind"
    assert row["status"] == "rejected"


@pytest.mark.known_bug(issue=539, backends=("python",))
def test_a_truncated_mkv_never_completes_as_if_it_were_whole(
    server_factory, client_factory, fake_managers, real_ffmpeg_env, tmp_path: Path
) -> None:
    ffmpeg = _tool(real_ffmpeg_env, "ffmpeg")
    good = tmp_path / "good-source.mkv"
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
            "testsrc=duration=3:size=64x64:rate=10",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:duration=3",
            "-map",
            "0:v",
            "-map",
            "1:a",
            "-c:v",
            "mpeg4",
            "-c:a",
            "mp2",
            str(good),
        ],
        check=True,
        capture_output=True,
    )
    data = good.read_bytes()

    folders = h.Folders.make(tmp_path)
    release = folders.watched / "Truncated.539"
    release.mkdir()
    source = release / "truncated.mkv"
    # Cut well short of the end: the container header still names the full duration (empirically
    # confirmed), so only an end-to-end integrity read can catch this.
    source.write_bytes(data[: len(data) * 60 // 100])

    server = server_factory(
        env={
            **real_ffmpeg_env,
            "WEIR_REFINER_WORKER_COUNT": "1",
            "WEIR_MEDIA_MANAGER_WEBHOOK_SECRET": h.WEBHOOK_SECRET,
        }
    )
    admin = client_factory(server)
    admin.ensure_admin()
    _fake, _library = h.deluno_setup(admin, fake_managers, folders)

    h.post_handoff(admin, handoff_id="handoff-truncated-539", source_path=source)

    h.never_within(
        lambda: h.handoff_status(admin, "handoff-truncated-539")["state"] == "completed",
        seconds=20,
        what="a truncated file to be wrongly reported completed with a false, pre-truncation duration",
    )
