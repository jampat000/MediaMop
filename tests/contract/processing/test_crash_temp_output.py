"""#534: a crash mid-remux must not leave the half-written temp output in the library's work folder.

The fake ffmpeg writes a partial output into the work folder before its delay, exactly where Weir's
remux temp file lives (``{stem}.processing.XXXXXXXX{suffix}``), so killing the server during that
delay reproduces the orphan. Python's startup recovery only removes ``.partial`` files from the
output folder, so the temp file survives there; the .NET server removes Weir's own temp names for
interrupted jobs and leaves every other file in the work folder alone.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.contract.processing import _helpers as h
from tests.contract.support.fake_ffmpeg import fake_media_bytes, probe
from tests.contract.support.polling import wait_until


def test_a_crash_mid_remux_leaves_no_temp_output_and_the_job_still_finishes(
    server_factory, client_factory, fake_ffmpeg, fake_managers, tmp_path: Path
) -> None:
    server = h.start_working_server(server_factory, fake_ffmpeg)
    admin = client_factory(server)
    admin.ensure_admin()
    folders = h.Folders.make(tmp_path)
    fake, _library = h.deluno_setup(admin, fake_managers, folders)
    fake_ffmpeg.set_file_rule("film.mkv", remux_delay_seconds=120)
    release = folders.watched / "Crash.Temp.534"
    release.mkdir()
    source = release / "film.mkv"
    source.write_bytes(fake_media_bytes(probe(audio_languages=("eng", "fre"))))
    operator_note = folders.work / "film.processing.notes.txt"
    operator_note.write_text("an operator's own file that happens to look similar")

    h.post_handoff(admin, handoff_id="handoff-temp-534", source_path=source)
    wait_until(
        lambda: list(folders.work.glob("film.processing.*.mkv")),
        timeout_s=60,
        what="the remux to start writing its temp output in the work folder",
    )

    server.kill()
    assert list(folders.work.glob("film.processing.*.mkv")), "the kill must leave the half-written temp output behind"
    fake_ffmpeg.set_file_rule("film.mkv")
    server.start()
    admin = client_factory(server)
    admin.login()

    h.wait_for_handoff_state(admin, "handoff-temp-534", "completed")
    assert (folders.output / "Crash.Temp.534" / "film.mkv").is_file()
    assert not list(folders.work.glob("film.processing.*.mkv")), "the interrupted job's temp output must be removed"
    assert operator_note.is_file(), "only Weir's own temp names are ever deleted"
    assert [r["status"] for r in h.callbacks(fake, "handoff-temp-534")] == ["completed"]
