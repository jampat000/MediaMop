"""Black-box processing: a media manager hands Weir a file and hears back.

Covers behaviour the backend tested only from the inside (test_processing_talks_to_media_managers.py,
test_media_manager_completion_callback.py, test_media_manager_intake_api.py's folder cases): a running
server, a fake Deluno, and fake ffprobe/ffmpeg.
"""

from __future__ import annotations

import json
from pathlib import Path

from tests.contract.processing import _helpers as h
from tests.contract.support.fake_ffmpeg import fake_media_bytes, probe
from tests.contract.support.polling import wait_until


def test_handoff_is_remuxed_and_reported_complete_with_the_managers_output_path(
    server_factory, client_factory, fake_ffmpeg, fake_managers, tmp_path: Path
) -> None:
    server = h.start_working_server(server_factory, fake_ffmpeg)
    admin = client_factory(server)
    admin.ensure_admin()
    folders = h.Folders.make(tmp_path)
    fake, _library = h.deluno_setup(admin, fake_managers, folders)

    release = folders.watched / "Blade.Runner.2049"
    release.mkdir()
    # English and French audio; the default rules keep English, so a remux is required.
    source = release / "film.mkv"
    source.write_bytes(fake_media_bytes(probe(audio_languages=("eng", "fre"))))

    accepted = h.post_handoff(admin, handoff_id="handoff-ok-1", source_path=source)
    assert accepted["status"] == "ok"
    assert accepted["event"] == "handoff"
    assert accepted["enqueued"] == h.REMUX_KIND

    done = h.wait_for_handoff_state(admin, "handoff-ok-1", "completed")
    report = fake.wait_for_request("POST", h.EVENTS_PATH)[0]
    assert report.header("X-Api-Key") == fake.api_key
    body = report.json
    assert body["handoffId"] == "handoff-ok-1"
    assert body["status"] == "completed"
    assert body["processorName"] == "Weir"
    assert body["libraryId"] == h.DELUNO_LIBRARY_KEY
    assert body["releaseName"] == "Contract.Release.2024"
    assert body["message"] == "Removed 1 audio track."
    # Rebuilt under the manager's own processor output folder, not Weir's local path.
    expected = f"{h.DELUNO_OUTPUT_ROOT}/Blade.Runner.2049/film.mkv"
    assert body["outputPath"].replace("\\", "/") == expected
    assert done["outputPath"].replace("\\", "/") == expected

    output = folders.output / "Blade.Runner.2049" / "film.mkv"
    assert output.is_file()
    remuxes = fake_ffmpeg.calls(tool="ffmpeg", step="remux")
    assert len(remuxes) == 1
    # The French track (input stream 2) was not mapped into the output.
    assert "0:2" not in remuxes[0]["argv"]
    # A successful Movies pass removes the release from the watched folder.
    wait_until(lambda: not release.exists(), timeout_s=30, what="the source release folder to be cleaned up")
    assert len(h.callbacks(fake, "handoff-ok-1")) == 1


def test_folder_handoff_with_a_sample_queues_and_processes_only_the_main_video(
    server_factory, client_factory, fake_ffmpeg, fake_managers, tmp_path: Path
) -> None:
    server = h.start_working_server(server_factory, fake_ffmpeg)
    admin = client_factory(server)
    admin.ensure_admin()
    folders = h.Folders.make(tmp_path)
    # Pause first, so the queue can be inspected before any work starts.
    h.set_pause(admin, paused=True)
    fake, _library = h.deluno_setup(admin, fake_managers, folders)

    release = folders.watched / "Some.Film.2020.1080p"
    (release / "Sample").mkdir(parents=True)
    main = release / "Some.Film.2020.1080p.mkv"
    main.write_bytes(fake_media_bytes(probe(audio_languages=("eng", "fre"))))
    (release / "Sample" / "some.film.sample.mkv").write_bytes(fake_media_bytes(probe()))
    (release / "Some.Film.2020.1080p.nfo").write_text("info", encoding="utf-8")

    h.post_handoff(admin, handoff_id="handoff-folder-1", source_path=release)

    remux_jobs = h.jobs(admin, kind=h.REMUX_KIND)
    assert len(remux_jobs) == 1
    payload = json.loads(remux_jobs[0]["payload_json"])
    assert payload["relative_media_path"] == "Some.Film.2020.1080p/Some.Film.2020.1080p.mkv"
    assert payload["origin"]["handoff_id"] == "handoff-folder-1"
    assert h.handoff_status(admin, "handoff-folder-1")["state"] == "queued"

    h.set_pause(admin, paused=False)
    h.wait_for_handoff_state(admin, "handoff-folder-1", "completed")
    probed = {call["file"] for call in fake_ffmpeg.calls(tool="ffprobe")}
    assert "some.film.sample.mkv" not in probed
    assert [c["file"] for c in fake_ffmpeg.calls(tool="ffmpeg", step="remux")] == ["Some.Film.2020.1080p.mkv"]
    reports = h.callbacks(fake, "handoff-folder-1")
    assert len(reports) == 1
    assert reports[0]["outputPath"].replace("\\", "/").endswith("Some.Film.2020.1080p/Some.Film.2020.1080p.mkv")
