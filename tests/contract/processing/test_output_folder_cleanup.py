"""Black-box processing: per-title output-folder cleanup after a successful pass.

Issue #545 item 1: cleanup used to treat "the manager reports no library files inside this
folder" as proof the folder is safe to remove, even when that is exactly what a manager that has
not scanned or finished importing yet looks like (or one that imports by copy and scans later).
The correct behaviour never deletes the folder until a manager has positive evidence of the
release, or the hand-off ledger already recorded the outcome as delivered.
"""

from __future__ import annotations

import os
import time
from pathlib import Path

import pytest

from tests.contract.processing import _helpers as h
from tests.contract.support.fake_ffmpeg import fake_media_bytes, probe
from tests.contract.support.polling import wait_until

# Comfortably past the movie output-cleanup minimum age, which both backends floor at one hour
# regardless of configuration (WEIR_REFINER_MOVIE_OUTPUT_CLEANUP_MIN_AGE_SECONDS is clamped to
# 3600s..30d). "pass_through_unchanged" forces the copy-without-remux path (a Windows hard link, or
# a copy that preserves metadata), which carries the source's own modification time onto the
# output, so backdating the source before enqueueing reaches that age immediately instead of
# making the test wait an hour.
_OLD_ENOUGH_SECONDS = 2 * 3600


def _signed_in_working_server(server_factory, client_factory, fake_ffmpeg):
    # The default minimum age (48h) would make this test wait that long for real; the environment
    # variable is clamped to 3600s..30d on both backends, so this is as low as it can go.
    server = h.start_working_server(
        server_factory, fake_ffmpeg, WEIR_REFINER_MOVIE_OUTPUT_CLEANUP_MIN_AGE_SECONDS="3600"
    )
    admin = client_factory(server)
    admin.ensure_admin()
    return server, admin


def _enqueue_pass_through_unchanged(admin, *, relative_media_path: str, library_id: int) -> None:
    r = admin.post_csrf(
        "/api/v1/refiner/jobs/file-remux-pass/enqueue",
        {"relative_media_path": relative_media_path, "library_id": library_id, "pass_through_unchanged": True},
    )
    assert r.status_code == 200, r.text


def _wait_for_the_pass_to_finish(admin) -> None:
    # A manual enqueue with no prior scan leaves no Files row for GET /refiner/files to report on
    # (mark_file_status is a no-op with nothing to update), so this watches the job itself — the
    # same reason the Radarr-queue scenario in test_failure_policies.py does the same.
    wait_until(
        lambda: any(j["status"] == "completed" for j in h.jobs(admin, kind=h.REMUX_KIND)) or None,
        timeout_s=60,
        what="the manual pass to finish",
    )


@pytest.mark.known_bug(issue=545, backends=("python",))
def test_output_folder_is_kept_when_the_manager_has_not_imported_yet(
    server_factory, client_factory, fake_ffmpeg, fake_managers, tmp_path: Path
) -> None:
    _server, admin = _signed_in_working_server(server_factory, client_factory, fake_ffmpeg)
    folders = h.Folders.make(tmp_path)
    radarr = fake_managers("radarr", root_folders=[str(tmp_path / "library")])
    connection = h.create_connection(admin, radarr)
    h.relax_operator_guards(admin)
    library = h.create_library(admin, folders, manager_connection_ids=[connection["id"]])

    release = folders.watched / "Contract.Movie.2024"
    release.mkdir()
    source = release / "Contract.Movie.2024.mkv"
    source.write_bytes(fake_media_bytes(probe(audio_languages=("eng",))))
    old = time.time() - _OLD_ENOUGH_SECONDS
    os.utime(source, (old, old))
    rel = "Contract.Movie.2024/Contract.Movie.2024.mkv"

    # The fake Radarr answers (it is reachable and reporting) but its own library listing stays
    # empty: exactly what a manager that has not scanned or finished importing this release yet
    # looks like. radarr.library is never populated in this test.
    _enqueue_pass_through_unchanged(admin, relative_media_path=rel, library_id=library["id"])
    _wait_for_the_pass_to_finish(admin)

    assert radarr.requests_to("GET", "/api/v3/movie"), "the folder-cleanup gate must have asked Radarr what it keeps"
    output_folder = folders.output / "Contract.Movie.2024"
    assert output_folder.is_dir(), (
        "the per-title output folder must not be deleted before a manager confirms this release was "
        "imported (or the hand-off ledger records the outcome as delivered) — reporting no *conflicting* "
        "files in the folder is not the same as reporting this release as imported"
    )
    assert (output_folder / "Contract.Movie.2024.mkv").is_file()


def test_output_folder_is_removed_once_the_manager_confirms_the_import(
    server_factory, client_factory, fake_ffmpeg, fake_managers, tmp_path: Path
) -> None:
    """Same shape as above, but the manager's library now names this release (moved to its own
    path, as a manager that renames or reorganises on import would record it) — the positive
    evidence the folder-cleanup gate looks for, so the folder is removed as before.
    """

    _server, admin = _signed_in_working_server(server_factory, client_factory, fake_ffmpeg)
    folders = h.Folders.make(tmp_path)
    radarr = fake_managers("radarr", root_folders=[str(tmp_path / "library")])
    connection = h.create_connection(admin, radarr)
    h.relax_operator_guards(admin)
    library = h.create_library(admin, folders, manager_connection_ids=[connection["id"]])

    release = folders.watched / "Confirmed.Movie.2024"
    release.mkdir()
    source = release / "Confirmed.Movie.2024.mkv"
    source.write_bytes(fake_media_bytes(probe(audio_languages=("eng",))))
    old = time.time() - _OLD_ENOUGH_SECONDS
    os.utime(source, (old, old))
    rel = "Confirmed.Movie.2024/Confirmed.Movie.2024.mkv"
    radarr.library.append({"movieFile": {"path": str(tmp_path / "library" / "Confirmed.Movie.2024.mkv")}})

    _enqueue_pass_through_unchanged(admin, relative_media_path=rel, library_id=library["id"])
    _wait_for_the_pass_to_finish(admin)

    output_folder = folders.output / "Confirmed.Movie.2024"
    assert not output_folder.exists(), "a manager that confirmed the import should let the folder be removed"
