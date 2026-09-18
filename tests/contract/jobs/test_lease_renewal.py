"""Correct behaviour for #540 item 1: a job that runs longer than its lease must never be claimed by
a second worker while the first is still running it.

On Python, nothing renews a lease: ``process_one_processing_job`` (``the retired Python backend's weir/processing/worker_loop.py``)
claims with a fixed ``lease_seconds=DEFAULT_PROCESSING_JOB_LEASE_SECONDS`` (300) and nothing extends it
while the handler runs, so a remux running longer than five minutes can be claimed by a second
worker while the first is still writing the same file. ``DEFAULT_PROCESSING_JOB_LEASE_SECONDS`` is a
plain Python constant with no ``WeirSettings`` field and no ``WEIR_*`` environment override anywhere
in ``core/config.py`` or ``worker_loop.py`` — confirmed by reading both — so there is no way from
outside the process to shrink the 300s lease for a test that can afford to wait past it.

On .NET, the lease-length knob and the fix both exist: ``WEIR_PROCESSING_JOB_LEASE_SECONDS``
(``WeirOptions.ProcessingJobLeaseSeconds``, clamped to 30..86400s) shortens the lease, and
``ProcessingJobProcessor.RunHandlerWithLeaseRenewalAsync`` runs a heartbeat that renews it roughly every
``lease_seconds / 3`` while the handler is still running — proven directly by the unit test
``Weir.Infrastructure.Tests/Jobs/LeaseRenewalTests.cs``. This contract-level test still cannot run
there, though: no ``IJobHandler`` is registered for ``processing.file.remux_pass.v1`` anywhere in this
build (confirmed by grepping ``: IJobHandler`` across ``apps/server/src``), so a webhook-enqueued
remux job never leaves ``pending`` — the processing engine's job handlers (remux pass etc.) are a
separate, not-yet-ported piece. Enable this once that handler exists, using
``@pytest.mark.backends("dotnet", reason=...)`` (python still has no lease knob).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.contract.processing import _helpers as h
from tests.contract.support.fake_ffmpeg import fake_media_bytes, probe

NO_END_TO_END_REMUX_YET = (
    "python has no WEIR_PROCESSING_JOB_LEASE_SECONDS override (see module docstring), and .NET has the "
    "lease knob and renewal heartbeat but no IJobHandler for processing.file.remux_pass.v1 yet, so no "
    "backend can run a webhook-enqueued remux to completion at contract speed; see #540 item 1"
)


@pytest.mark.skip(reason=NO_END_TO_END_REMUX_YET)
def test_a_job_longer_than_its_lease_is_never_claimed_twice(
    server_factory, client_factory, fake_ffmpeg, fake_managers, tmp_path: Path
) -> None:
    # Two workers sharing one database; a remux that runs long enough to outlive a short lease
    # must still only ever be claimed by one of them. 30s is the minimum WEIR_PROCESSING_JOB_LEASE_SECONDS
    # accepts (WeirOptionsLoader.ClampProcessingJobLeaseSeconds); the heartbeat renews it about every 10s,
    # so a 45s remux leaves a comfortable window (past the 5s idle poll) where a second worker would
    # have claimed the row already if renewal were broken.
    server = server_factory(
        env={
            **h.working_env(fake_ffmpeg),
            "WEIR_PROCESSING_WORKER_COUNT": "2",
            "WEIR_PROCESSING_JOB_LEASE_SECONDS": "30",
        }
    )
    admin = client_factory(server)
    admin.ensure_admin()
    folders = h.Folders.make(tmp_path)
    _fake, _library = h.deluno_setup(admin, fake_managers, folders)
    # Deliberately longer than the lease, so a heartbeat is required to keep the lease alive for the
    # whole run; the fake ffmpeg reports its steps as it goes either way.
    fake_ffmpeg.set_file_rule("film.mkv", probe=probe(), remux_delay_seconds=45)
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
