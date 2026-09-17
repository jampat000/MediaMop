"""Correct behaviour for #531: hand-off retries must not reset the failure count, and must not lose
the hand-off's origin when a scan requeues the file.

Root causes, read from the source while writing these tests (both in
``refiner_watched_folder_remux_scan_dispatch_handlers.py`` and friends):

- Item 1: a hand-off's file has no recorded size until a scan sees it: ``record_failure``
  (``refiner_requeue_service.py``) creates the Files row on the first execution failure but never
  sets ``size_bytes``, so it stays ``None``. The *first* scan afterwards
  (``refiner_watched_folder_remux_scan_dispatch_handlers.py``) compares ``previous.size_bytes !=
  observed_size`` — ``None != <real size>`` — and resets ``failure_attempts`` to 0, exactly once,
  because that same scan pass also records the real size (so later scans see no change). The
  workaround (``tests/contract/processing/_helpers.py``'s ``detect_without_queueing``) runs a
  size-recording scan before the hand-off; the test below deliberately skips it and instead checks
  the fingerprint and the reset directly, because a test that only waits for the eventual
  failure-attempts count would still reach it after the one-time reset and falsely pass.
- Item 2: the payload a scan-driven retry builds (``payload_body`` in
  ``refiner_watched_folder_remux_scan_dispatch_handlers.py``) never copies the job's ``origin``.
  ``completion_callback.report_handoff_completion`` reads ``origin`` from the payload and returns
  immediately when it is ``None`` — before posting anything *and* before recording the ledger's own
  ``output_path`` — so once a file has been retried even once, its eventual pass-through is reported
  to nobody: no callback, and ``GET /intake/handoffs/{source}/{id}`` keeps ``outputPath: null``
  forever. See the comment on ``test_failure_is_retried_then_the_original_is_passed_through_unchanged``
  in ``test_failure_policies.py``: its ``all(report["status"] != "failed" ...)`` assertion is true
  today only because the callback list is empty, not because a real completion was reported.

dotnet fixed item 2 too: ``RefinerWatchedFolderScanDispatchJobHandler.EnqueueRemuxPassAsync`` (the scan's
own automatic retry path — the same method used for a fresh candidate) now looks up
``HandoffOriginCarry.FindAsync`` and copies ``origin`` onto the requeued job's payload, the same fix
``RequeueStore.RequeueFileAsync`` already applied to the manual-retry half (#531 item 2).
"""

from __future__ import annotations

from pathlib import Path

from tests.contract.processing import _helpers as h
from tests.contract.support.fake_ffmpeg import fake_media_bytes, probe
from tests.contract.support.polling import wait_until

REMUX_CRASH = "Conversion failed: the fake ffmpeg was told to fail"


# dotnet fixed by this integration: the watched-folder scan's automatic retry (previous.Status ==
# ProcessingFailed, due for another attempt) used to enqueue through RequeueStore.RequeueFileAsync, whose
# "manual retry" reset (failure_attempts back to 0, backoff cleared) is meant for a human's "retry now", not
# an automatic, policy-governed retry — RetryPolicy/RecordFailureAsync own that. Every scan cycle silently
# wiped the counter this test checks. Fixed by enqueueing the same way a fresh candidate would instead.
def test_a_hand_offs_fingerprint_is_recorded_up_front_so_a_scan_never_resets_its_failures(
    server_factory, client_factory, fake_ffmpeg, fake_managers, tmp_path: Path
) -> None:
    server = h.start_working_server(server_factory, fake_ffmpeg)
    admin = client_factory(server)
    admin.ensure_admin()
    folders = h.Folders.make(tmp_path)
    _fake, library = h.deluno_setup(
        admin, fake_managers, folders, failure_policy="hold", max_attempts=10, retry_backoff_seconds=1
    )
    fake_ffmpeg.set_file_rule("film.mkv", remux_error=REMUX_CRASH)
    release = folders.watched / "Always.Broken.531"
    release.mkdir()
    source = release / "film.mkv"
    source.write_bytes(fake_media_bytes(probe(audio_languages=("eng",))))
    rel = "Always.Broken.531/film.mkv"

    # No detect_without_queueing: a hand-off's fingerprint must be recorded on arrival, not by a
    # scan run first as a workaround.
    h.post_handoff(admin, handoff_id="handoff-attempts-531", source_path=source)

    first = h.wait_for_file_status(admin, library["id"], rel, "processing_failed")
    assert first["failure_attempts"] == 1
    assert int(first["size_bytes"] or 0) > 0, (
        "a hand-off must record the file's size at intake, not leave it for the first scan to discover"
    )

    # A scan that merely notices this (already-known) file must not treat it as a changed source.
    # ``enqueue_remux_jobs=False`` only skips queueing new remux work — the size comparison (and the
    # bugged reset) run regardless, so this isolates the effect of the scan itself.
    h.enqueue_scan(admin, library, enqueue_remux_jobs=False)

    def _seen_again() -> dict | None:
        row = h.file_row(admin, library["id"], rel)
        return row if row is not None and row["last_seen_at"] else None

    settled = wait_until(_seen_again, timeout_s=30, what="the scan to finish noticing this file")
    assert settled["status"] == "processing_failed", settled
    assert settled["failure_attempts"] == 1, "an intervening scan must not reset the failure count (#531 item 1)"


def test_pass_through_after_a_retry_reports_a_completion_callback_with_output_path(
    server_factory, client_factory, fake_ffmpeg, fake_managers, tmp_path: Path
) -> None:
    server = h.start_working_server(server_factory, fake_ffmpeg)
    admin = client_factory(server)
    admin.ensure_admin()
    folders = h.Folders.make(tmp_path)
    fake, library = h.deluno_setup(
        admin, fake_managers, folders, failure_policy="pass_through", max_attempts=2, retry_backoff_seconds=1
    )
    fake_ffmpeg.set_file_rule("film.mkv", remux_error=REMUX_CRASH)
    release = folders.watched / "Broken.Origin.531"
    release.mkdir()
    source = release / "film.mkv"
    original = fake_media_bytes(probe(audio_languages=("eng", "fre")))
    source.write_bytes(original)
    rel = "Broken.Origin.531/film.mkv"

    # No detect_without_queueing here either: the very first scan a failure schedules is the one
    # that (today) drops the origin, so the scenario must go through at least one such retry.
    h.post_handoff(admin, handoff_id="handoff-origin-531", source_path=source)

    h.drive_retries_until(
        admin,
        library,
        lambda: h.handoff_status(admin, "handoff-origin-531")["state"] == "passed-through",
        what="the hand-off to be passed through after a retry",
    )

    delivered = folders.output / "Broken.Origin.531" / "film.mkv"
    assert delivered.read_bytes() == original

    status = h.handoff_status(admin, "handoff-origin-531")
    assert status["outputPath"], "the origin (and so the output path) must survive a scan-driven retry"
    # deluno_setup's manifest declares a "refine-before-import" library with its own processorOutputPath,
    # so — same as a first-attempt pass-through, see test_handoff_scenarios.py's
    # test_handoff_is_remuxed_and_reported_complete_with_the_managers_output_path — the reported path is
    # rebuilt under the manager's own root, not Weir's local output folder.
    expected = f"{h.DELUNO_OUTPUT_ROOT}/Broken.Origin.531/film.mkv"
    assert status["outputPath"].replace("\\", "/") == expected

    reports = h.callbacks(fake, "handoff-origin-531")
    assert reports, "a retried-then-passed-through hand-off must still report a completion callback"
    assert reports[-1].get("outputPath")
