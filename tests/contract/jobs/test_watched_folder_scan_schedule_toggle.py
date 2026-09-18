"""Correct behaviour for #533: the switch to turn off periodic watched-folder scans must do so.

On Python, ``WEIR_PROCESSING_WATCHED_FOLDER_REMUX_SCAN_DISPATCH_SCHEDULE_ENABLED`` is documented and
present in settings, but nothing in ``WeirSettings`` even parses it (see ``core/config.py``) and
``processing_library_periodic_scan_enabled`` (``processing_watched_folder_remux_scan_dispatch_periodic_enqueue.py``)
only checks the library's own ``enabled`` flag. Its sibling,
``WEIR_PROCESSING_WATCHED_FOLDER_REMUX_SCAN_DISPATCH_PERIODIC_ENQUEUE_REMUX_JOBS``, only stops *remux*
jobs from being queued off a scan's findings — the scan itself still runs and still enqueues its own
``processing.watched_folder.remux_scan_dispatch.v1`` job. See the comment on this in
``tests/contract/support/launcher.py``, which the whole suite works around by leaving the periodic
timer alone and only counting the jobs a test itself caused.

Fixed in the .NET port (ProcessingWatchedFolderScanDispatchScheduleTask, apps/server/src/Weir.Infrastructure/
Jobs): the environment variable is parsed into WeirOptions and read every tick as a global kill switch,
alongside a second, independent per-scope check (the operator settings screen's Movies/TV periodic-scan
switch, itself equally dead in Python). Not fixed in Python — the backend is being retired (ADR-0017).

No ``known_bug`` marker here: within the short window these tests can afford, Python does not queue a
periodic scan for this library either way (switch on or off) — its periodic loop appears not to have
taken its first tick yet this soon after a restart, which this black-box timing test cannot tell apart
from "correctly disabled". The dead code is still real (grep core/config.py and
processing_watched_folder_remux_scan_dispatch_periodic_enqueue.py: the switch is parsed nowhere and
processing_scope_periodic_scan_enabled is never called), but this particular test cannot demonstrate it
within a contract-suite time budget, so it is not marked as a reproduced known bug. The .NET fix is
proven two ways: directly here (both tests pass against dotnet), and deterministically with a controlled
clock in Weir.Infrastructure.Tests.Jobs.ProcessingWatchedFolderScanDispatchScheduleTaskTests, which ticks the
scheduler many times over simulated minutes without waiting in real time.
"""

from __future__ import annotations

import time
from pathlib import Path

from tests.contract.jobs._helpers import job_by_id, library_for_scope, save_library
from tests.contract.support import seed
from tests.contract.support.client import API, WeirClient
from tests.contract.support.launcher import ServerUnderTest
from tests.contract.support.polling import wait_until

SCAN_KIND = "processing.watched_folder.remux_scan_dispatch.v1"
ENQUEUE = f"{API}/processing/jobs/watched-folder-remux-scan-dispatch/enqueue"
# The scheduler clamps every library's cadence to at least 10s (_watched_folder_scan_interval_seconds).
SHORT_INTERVAL_SECONDS = 10


def _scan_job_count(admin: WeirClient) -> int:
    r = admin.get(f"{API}/processing/jobs/inspection", params={"limit": 100})
    assert r.status_code == 200, r.text
    return sum(1 for job in r.json()["jobs"] if job["job_kind"] == SCAN_KIND)


def _never_within(check, *, seconds: float, what: str) -> None:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        assert not check(), f"{what} happened, but it must not"
        time.sleep(0.5)


def test_disabling_the_periodic_scan_switch_stops_the_scan_timer(
    server_factory, client_factory, tmp_path: Path
) -> None:
    watched = tmp_path / "watched"
    watched.mkdir()
    output = tmp_path / "output"
    output.mkdir()
    sut: ServerUnderTest = server_factory(env={"WEIR_PROCESSING_WATCHED_FOLDER_REMUX_SCAN_DISPATCH_SCHEDULE_ENABLED": "0"})
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

    # Restart (same env, switch still off) so the scheduler's first tick after this sees the library
    # already configured. Without this, "nothing happened yet" can just mean the first tick raced this
    # test's own setup and saw an unready library — true on either backend regardless of the switch —
    # rather than proving the switch itself stopped anything.
    with seed.stopped(sut):
        pass
    admin = client_factory(sut)
    admin.ensure_admin()

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


def test_periodic_scan_switch_left_on_lets_the_scan_timer_run(server_factory, client_factory, tmp_path: Path) -> None:
    """Positive control for the test above: with the switch untouched (on by default), the same
    library, on the same short cadence, must eventually get a periodic scan — proving the negative
    result above is the switch actually working, not the timer coincidentally never firing in time."""

    watched = tmp_path / "watched"
    watched.mkdir()
    output = tmp_path / "output"
    output.mkdir()
    sut: ServerUnderTest = server_factory()
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

    # Restart so the scheduler's first tick sees the library already configured, rather than racing
    # this test's own setup calls and locking in a stale "not ready yet" due time for a full interval
    # (that race is real: the scheduler can queue its first attempt almost as soon as the process is up,
    # which is often before this test's own HTTP setup calls above land).
    with seed.stopped(sut):
        pass
    admin = client_factory(sut)
    admin.ensure_admin()

    # No manual scan preceded this, so any scan-dispatch job at all here is the periodic timer's doing —
    # RunAtStart can fire it before this line even runs, so this checks for one rather than a delta.
    wait_until(
        lambda: _scan_job_count(admin) > 0,
        timeout_s=SHORT_INTERVAL_SECONDS + 20,
        interval_s=0.5,
        what="a periodic scan-dispatch job with the switch on",
    )
