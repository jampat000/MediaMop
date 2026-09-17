"""Correct behaviour for #540 item 1: a job that runs longer than its lease must never be claimed by
a second worker while the first is still running it.

Today nothing renews a lease: ``process_one_refiner_job`` (``apps/backend/src/weir/refiner/worker_loop.py``)
claims with a fixed ``lease_seconds=DEFAULT_REFINER_JOB_LEASE_SECONDS`` (300) and nothing extends it
while the handler runs, so a remux running longer than five minutes can be claimed by a second
worker while the first is still writing the same file.

This cannot be proven at contract speed today. ``DEFAULT_REFINER_JOB_LEASE_SECONDS`` is a plain
Python constant (``worker_loop.py``) with no ``WeirSettings`` field and no ``WEIR_*`` environment
override anywhere in ``core/config.py`` or ``worker_loop.py`` — confirmed by reading both — so there
is no way from outside the process to shrink the 300s lease for a test that can afford to wait past
it. The test below is written for the correct behaviour and is skipped until a lease-length knob
(e.g. an env-overridable ``WEIR_REFINER_JOB_LEASE_SECONDS``) exists; enable it by removing the
``skip`` marker and un-commenting the override once one lands, in the same change that adds the
heartbeat/renewal fix.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.contract.processing import _helpers as h
from tests.contract.support.fake_ffmpeg import fake_media_bytes, probe

LEASE_KNOB_MISSING = (
    "no environment override for the refiner job lease length exists yet "
    "(DEFAULT_REFINER_JOB_LEASE_SECONDS is a hardcoded 300s in worker_loop.py); see #540 item 1"
)


@pytest.mark.skip(reason=LEASE_KNOB_MISSING)
def test_a_job_longer_than_its_lease_is_never_claimed_twice(
    server_factory, client_factory, fake_ffmpeg, fake_managers, tmp_path: Path
) -> None:
    # Two workers sharing one database; a remux that runs long enough to outlive a short lease
    # (once one can be configured) must still only ever be claimed by one of them.
    server = server_factory(
        env={
            **h.working_env(fake_ffmpeg),
            "WEIR_REFINER_WORKER_COUNT": "2",
            # Enable once a lease-length override exists, with a lease shorter than remux_delay_seconds
            # below (e.g. "WEIR_REFINER_JOB_LEASE_SECONDS": "3").
        }
    )
    admin = client_factory(server)
    admin.ensure_admin()
    folders = h.Folders.make(tmp_path)
    _fake, _library = h.deluno_setup(admin, fake_managers, folders)
    # Deliberately longer than the (future) short lease, so a heartbeat is required to keep the
    # lease alive for the whole run; the fake ffmpeg reports its steps as it goes either way.
    fake_ffmpeg.set_file_rule("film.mkv", probe=probe(), remux_delay_seconds=30)
    release = folders.watched / "Long.Running.540"
    release.mkdir()
    source = release / "film.mkv"
    source.write_bytes(fake_media_bytes(probe()))

    h.post_handoff(admin, handoff_id="handoff-lease-540", source_path=source)
    h.wait_for_handoff_state(admin, "handoff-lease-540", "completed", timeout_s=120)

    # Only one remux call for this file must ever have started: a second worker claiming the same
    # row mid-write would show up here as two "remux" calls for film.mkv instead of one.
    assert len(h.jobs(admin, kind=h.REMUX_KIND)) == 1
    assert len(fake_ffmpeg.calls(tool="ffmpeg", step="remux")) == 1
