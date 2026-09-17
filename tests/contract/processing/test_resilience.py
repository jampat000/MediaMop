"""Black-box processing: work that is interrupted, paused, or outside its schedule.

Covers behaviour the backend tested from the inside in test_startup_crash_recovery.py and
test_refiner_schedules_and_pause.py.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from tests.contract.processing import _helpers as h
from tests.contract.support.client import API
from tests.contract.support.fake_ffmpeg import fake_media_bytes, probe
from tests.contract.support.polling import wait_until

SLOTS_PER_DAY = 96


def _source(folders: h.Folders, release: str) -> Path:
    folder = folders.watched / release
    folder.mkdir()
    source = folder / "film.mkv"
    source.write_bytes(fake_media_bytes(probe(audio_languages=("eng", "fre"))))
    return source


def test_server_killed_mid_job_recovers_the_job_on_restart_and_finishes_it(
    server_factory, client_factory, fake_ffmpeg, fake_managers, tmp_path: Path
) -> None:
    server = h.start_working_server(server_factory, fake_ffmpeg)
    admin = client_factory(server)
    admin.ensure_admin()
    folders = h.Folders.make(tmp_path)
    fake, _library = h.deluno_setup(admin, fake_managers, folders)
    # The first remux hangs long enough to be killed in the middle of it.
    fake_ffmpeg.set_file_rule("film.mkv", remux_delay_seconds=120)
    source = _source(folders, "Crash.Test.2020")

    h.post_handoff(admin, handoff_id="handoff-crash-1", source_path=source)
    wait_until(lambda: fake_ffmpeg.calls(tool="ffmpeg", step="remux"), timeout_s=60, what="the remux to start")
    assert h.handoff_status(admin, "handoff-crash-1")["state"] == "working"

    server.kill()
    fake_ffmpeg.set_file_rule("film.mkv")
    server.start()
    admin = client_factory(server)
    admin.login()

    h.wait_for_handoff_state(admin, "handoff-crash-1", "completed")
    assert len(fake_ffmpeg.calls(tool="ffmpeg", step="remux")) == 2
    assert (folders.output / "Crash.Test.2020" / "film.mkv").is_file()
    reports = h.callbacks(fake, "handoff-crash-1")
    assert [r["status"] for r in reports] == ["completed"]
    remux_jobs = h.jobs(admin, kind=h.REMUX_KIND)
    assert len(remux_jobs) == 1
    assert remux_jobs[0]["status"] == "completed"
    assert remux_jobs[0]["attempt_count"] == 2
    # Nothing half-written is published: no partial file in the output folder.
    assert not list(folders.output.rglob("*.partial"))


def test_pause_stops_new_work_until_resumed(
    server_factory, client_factory, fake_ffmpeg, fake_managers, tmp_path: Path
) -> None:
    server = h.start_working_server(server_factory, fake_ffmpeg)
    admin = client_factory(server)
    admin.ensure_admin()
    folders = h.Folders.make(tmp_path)
    fake, _library = h.deluno_setup(admin, fake_managers, folders)
    paused = h.set_pause(admin, paused=True)
    assert paused["reason"].startswith("Processing is paused")
    source = _source(folders, "Paused.Film.2021")

    h.post_handoff(admin, handoff_id="handoff-paused-1", source_path=source)
    # Several worker passes happen in this time; none may start the file.
    h.never_within(lambda: bool(fake_ffmpeg.calls()), seconds=12, what="ffprobe/ffmpeg running while paused")
    assert h.handoff_status(admin, "handoff-paused-1")["state"] == "queued"
    assert [j["status"] for j in h.jobs(admin, kind=h.REMUX_KIND)] == ["pending"]
    assert h.callbacks(fake, "handoff-paused-1") == []

    h.set_pause(admin, paused=False)
    h.wait_for_handoff_state(admin, "handoff-paused-1", "completed")
    assert len(fake_ffmpeg.calls(tool="ffmpeg", step="remux")) == 1


def _grid_closed_around(now_local: datetime, hours: int = 3) -> str:
    """Open all week except ``hours`` either side of ``now_local``."""

    grid = ["1"] * (7 * SLOTS_PER_DAY)
    start = now_local - timedelta(hours=hours)
    for quarter in range(hours * 2 * 4):
        moment = start + timedelta(minutes=15 * quarter)
        index = moment.weekday() * SLOTS_PER_DAY + moment.hour * 4 + moment.minute // 15
        grid[index] = "0"
    return "".join(grid)


def test_schedule_window_blocks_work_outside_its_hours(
    server_factory, client_factory, fake_ffmpeg, fake_managers, tmp_path: Path
) -> None:
    server = h.start_working_server(server_factory, fake_ffmpeg)
    admin = client_factory(server)
    admin.ensure_admin()
    folders = h.Folders.make(tmp_path)
    r = admin.get(f"{API}/suite/settings")
    assert r.status_code == 200, r.text
    timezone_name = r.json().get("app_timezone") or "UTC"
    closed_now = _grid_closed_around(datetime.now(UTC).astimezone(ZoneInfo(timezone_name)))
    fake, library = h.deluno_setup(admin, fake_managers, folders, schedule_enabled=True, schedule_grid=closed_now)
    assert library["schedule_grid"] == closed_now
    source = _source(folders, "Night.Only.2022")

    h.post_handoff(admin, handoff_id="handoff-window-1", source_path=source)
    h.never_within(lambda: bool(fake_ffmpeg.calls()), seconds=12, what="ffprobe/ffmpeg running outside the window")
    assert h.handoff_status(admin, "handoff-window-1")["state"] == "queued"
    assert [j["status"] for j in h.jobs(admin, kind=h.REMUX_KIND)] == ["pending"]

    # Opening the window lets the waiting job start.
    h.update_library(admin, library, schedule_grid="")
    h.wait_for_handoff_state(admin, "handoff-window-1", "completed")
    assert [r["status"] for r in h.callbacks(fake, "handoff-window-1")] == ["completed"]
