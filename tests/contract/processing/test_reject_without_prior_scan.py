"""Correct behaviour for #532: a rejected hand-off must have a Files row even when no watched-folder
scan ever saw the file first.

Root cause, read from the source: ``reject_bad_release`` (``processing_pass_through.py``) marks the
file's status through ``mark_file_status`` (``processing_file_state_service.py``), which only *updates*
an existing ``files`` row — ``if row is None: return None`` — rather than upserting one. A
hand-off Weir has never scanned has no row, so the rejection is silently dropped everywhere except
Activity.

This also needed the 500 fix from #530 (``ProcessingFileOut.status`` does not list ``rejected``), exactly
as the issue notes. Fixed on dotnet (#522 part 4): ``ProcessingRejectHandler`` upserts the Files row
(``RemuxPassFileState.UpsertRejectedAsync``) instead of the update-only ``mark_file_status``. The
Python backend is being retired (ADR-0017) and keeps the bug.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.contract.processing import _helpers as h
from tests.contract.support.fake_ffmpeg import fake_media_bytes, probe


def test_a_rejection_with_no_prior_scan_still_creates_a_files_row(
    server_factory, client_factory, fake_ffmpeg, fake_managers, tmp_path: Path
) -> None:
    server = h.start_working_server(server_factory, fake_ffmpeg)
    admin = client_factory(server)
    admin.ensure_admin()
    folders = h.Folders.make(tmp_path)
    fake, library = h.deluno_setup(
        admin,
        fake_managers,
        folders,
        capabilities=["processor-reject-regrab"],
        failure_policy="reject",
    )
    release = folders.watched / "No.Prior.Scan.532"
    release.mkdir()
    source = release / "film.mkv"
    # A video with no audio at all: content the reject policy blocklists outright.
    source.write_bytes(fake_media_bytes(probe(audio_languages=())))
    rel = "No.Prior.Scan.532/film.mkv"

    # No detect_without_queueing, no enqueue_scan: nothing but the hand-off itself has ever looked
    # at this file. That is the exact scenario the issue describes.
    h.post_handoff(admin, handoff_id="handoff-noscan-532", source_path=source)
    h.wait_for_handoff_state(admin, "handoff-noscan-532", "rejected")

    row = h.wait_for_file_status(admin, library["id"], rel, "rejected", timeout_s=30)
    assert "no retainable audio" in row["status_reason"]
