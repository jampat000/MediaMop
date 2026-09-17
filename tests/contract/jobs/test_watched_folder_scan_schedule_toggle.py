"""Correct behaviour for #533: the switch to turn off periodic watched-folder scans must do so.

``WEIR_REFINER_WATCHED_FOLDER_REMUX_SCAN_DISPATCH_SCHEDULE_ENABLED`` is documented and present in
settings, but nothing in ``WeirSettings`` even parses it (see ``core/config.py``) and
``refiner_library_periodic_scan_enabled`` (``refiner_watched_folder_remux_scan_dispatch_periodic_enqueue.py``)
only checks the library's own ``enabled`` flag. Its sibling,
``WEIR_REFINER_WATCHED_FOLDER_REMUX_SCAN_DISPATCH_PERIODIC_ENQUEUE_REMUX_JOBS``, only stops *remux*
jobs from being queued off a scan's findings — the scan itself still runs and still enqueues its own
``refiner.watched_folder.remux_scan_dispatch.v1`` job. See the comment on this in
``tests/contract/support/launcher.py``, which the whole suite works around by leaving the periodic
timer alone and only counting the jobs a test itself caused.
"""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from tests.contract.jobs._helpers import job_by_id, library_for_scope, save_library
from tests.contract.support.client import API, WeirClient
from tests.contract.support.launcher import ServerUnderTest

SCAN_KIND = "refiner.watched_folder.remux_scan_dispatch.v1"
ENQUEUE = f"{API}/refiner/jobs/watched-folder-remux-scan-dispatch/enqueue"
# The scheduler clamps every library's cadence to at least 10s (_watched_folder_scan_interval_seconds).
SHORT_INTERVAL_SECONDS = 10


def _scan_job_count(admin: WeirClient) -> int:
    r = admin.get(f"{API}/refiner/jobs/inspection", params={"limit": 500})
    assert r.status_code == 200, r.text
    return sum(1 for job in r.json()["jobs"] if job["job_kind"] == SCAN_KIND)


def _never_within(check, *, seconds: float, what: str) -> None:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        assert not check(), f"{what} happened, but it must not"
        time.sleep(0.5)


@pytest.mark.known_bug(issue=533, backends=("python", "dotnet"))
def test_disabling_the_periodic_scan_switch_stops_the_scan_timer(
    server_factory, client_factory, tmp_path: Path
) -> None:
    watched = tmp_path / "watched"
    watched.mkdir()
    output = tmp_path / "output"
    output.mkdir()
    sut: ServerUnderTest = server_factory(env={"WEIR_REFINER_WATCHED_FOLDER_REMUX_SCAN_DISPATCH_SCHEDULE_ENABLED": "0"})
    admin = client_factory(sut)
    admin.ensure_admin()
    movie = library_for_scope(admin, "movie")
    save_library(
        admin,
        movie["id"],
        watched_folder=str(watched),
        output_folder=str(output),
        scan_interval_seconds=SHORT_INTERVAL_SECONDS,
        skip_access_tests=True,
    )

    before = _scan_job_count(admin)
    _never_within(
        lambda: _scan_job_count(admin) > before,
        seconds=SHORT_INTERVAL_SECONDS * 2 + 5,
        what="a periodic scan-dispatch job with the switch off",
    )

    # A manual scan must still work regardless of the periodic switch.
    manual = admin.post_csrf(ENQUEUE, {"enqueue_remux_jobs": False})
    assert manual.status_code == 200, manual.text
    job = job_by_id(admin, manual.json()["job_id"])
    assert job["job_kind"] == SCAN_KIND
