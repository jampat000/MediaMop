"""Refiner Pass 4: failed import message taxonomy and terminal-over-pending precedence."""

from __future__ import annotations

from mediamop.modules.refiner.failed_import_classification import (
    FailedImportOutcome,
    classify_failed_import_message,
    normalize_failed_import_blob,
)


def test_pure_pending_waiting_downloaded_waiting_to_import() -> None:
    assert (
        classify_failed_import_message("Downloaded - Waiting to Import")
        == FailedImportOutcome.PENDING_WAITING
    )


def test_pure_pending_waiting_case_and_whitespace_insensitive() -> None:
    blob = "  downloaded   -   waiting   to   import  "
    assert classify_failed_import_message(blob) == FailedImportOutcome.PENDING_WAITING


def test_pure_pending_import_pending_phrase() -> None:
    assert classify_failed_import_message("Import pending") == FailedImportOutcome.PENDING_WAITING


def test_quality_not_an_upgrade_for_existing_movie_file() -> None:
    assert (
        classify_failed_import_message("Not an upgrade for existing movie file")
        == FailedImportOutcome.QUALITY
    )


def test_unmatched_manual_import_required() -> None:
    assert (
        classify_failed_import_message("Manual Import required")
        == FailedImportOutcome.UNMATCHED
    )


def test_corrupt_unreadable_signals() -> None:
    assert classify_failed_import_message("The file is corrupt") == FailedImportOutcome.CORRUPT
    assert classify_failed_import_message("unreadable data") == FailedImportOutcome.CORRUPT
    assert classify_failed_import_message("Checksum failed") == FailedImportOutcome.CORRUPT


def test_download_failed_download_client_signals() -> None:
    assert (
        classify_failed_import_message("Download failed: timeout")
        == FailedImportOutcome.DOWNLOAD_FAILED
    )
    assert (
        classify_failed_import_message("Unable to connect to the remote download client")
        == FailedImportOutcome.DOWNLOAD_FAILED
    )


def test_import_failed_generic_phrase() -> None:
    assert classify_failed_import_message("Import failed") == FailedImportOutcome.IMPORT_FAILED
    assert (
        classify_failed_import_message("Could not import movie")
        == FailedImportOutcome.IMPORT_FAILED
    )


def test_terminal_manual_import_beats_waiting_in_same_blob() -> None:
    """Terminal rejection beats pending-waiting when both appear in one blob."""
    blob = (
        "Downloaded - Waiting to Import. "
        "Manual Import required for the release."
    )
    assert classify_failed_import_message(blob) == FailedImportOutcome.UNMATCHED


def test_terminal_quality_beats_waiting_in_same_blob() -> None:
    blob = "Waiting to import — Not an upgrade for existing movie file"
    assert classify_failed_import_message(blob) == FailedImportOutcome.QUALITY


def test_terminal_corrupt_beats_waiting_in_same_blob() -> None:
    blob = "Import pending; file is corrupt"
    assert classify_failed_import_message(blob) == FailedImportOutcome.CORRUPT


def test_unknown_when_no_signal() -> None:
    assert classify_failed_import_message("") == FailedImportOutcome.UNKNOWN
    assert classify_failed_import_message("   ") == FailedImportOutcome.UNKNOWN
    assert classify_failed_import_message("Something else entirely.") == FailedImportOutcome.UNKNOWN


def test_normalize_failed_import_blob_contract() -> None:
    assert normalize_failed_import_blob("  A  B\nC  ") == "a b c"
