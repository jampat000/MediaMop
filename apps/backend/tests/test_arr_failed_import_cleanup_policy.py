"""Failed import cleanup policy 1:1 with classifier outcomes."""

from __future__ import annotations

from mediamop.modules.arr_failed_import.classification import FailedImportOutcome
from mediamop.modules.arr_failed_import.policy import (
    FailedImportCleanupPolicy,
    FailedImportCleanupPolicyKey,
    cleanup_policy_key_for_outcome,
    default_failed_import_cleanup_policy,
    is_failed_import_cleanup_enabled,
)


def test_each_terminal_outcome_maps_to_distinct_policy_key() -> None:
    terminals = (
        FailedImportOutcome.QUALITY,
        FailedImportOutcome.UNMATCHED,
        FailedImportOutcome.CORRUPT,
        FailedImportOutcome.DOWNLOAD_FAILED,
        FailedImportOutcome.IMPORT_FAILED,
    )
    keys = {cleanup_policy_key_for_outcome(o) for o in terminals}
    assert len(keys) == 5
    assert None not in keys


def test_no_two_terminal_outcomes_share_same_policy_key() -> None:
    terminals = (
        FailedImportOutcome.QUALITY,
        FailedImportOutcome.UNMATCHED,
        FailedImportOutcome.CORRUPT,
        FailedImportOutcome.DOWNLOAD_FAILED,
        FailedImportOutcome.IMPORT_FAILED,
    )
    mapped = [cleanup_policy_key_for_outcome(o) for o in terminals]
    assert len(mapped) == len(set(mapped))


def test_quality_maps_to_remove_quality_rejections_key() -> None:
    assert cleanup_policy_key_for_outcome(FailedImportOutcome.QUALITY) == (
        FailedImportCleanupPolicyKey.REMOVE_QUALITY_REJECTIONS
    )


def test_unmatched_maps_to_manual_import_rejections_key() -> None:
    assert cleanup_policy_key_for_outcome(FailedImportOutcome.UNMATCHED) == (
        FailedImportCleanupPolicyKey.REMOVE_UNMATCHED_MANUAL_IMPORT_REJECTIONS
    )


def test_corrupt_maps_to_corrupt_imports_key() -> None:
    assert cleanup_policy_key_for_outcome(FailedImportOutcome.CORRUPT) == (
        FailedImportCleanupPolicyKey.REMOVE_CORRUPT_IMPORTS
    )


def test_download_failed_maps_to_failed_downloads_key() -> None:
    assert cleanup_policy_key_for_outcome(FailedImportOutcome.DOWNLOAD_FAILED) == (
        FailedImportCleanupPolicyKey.REMOVE_FAILED_DOWNLOADS
    )


def test_import_failed_maps_to_failed_imports_key() -> None:
    assert cleanup_policy_key_for_outcome(FailedImportOutcome.IMPORT_FAILED) == (
        FailedImportCleanupPolicyKey.REMOVE_FAILED_IMPORTS
    )


def test_pending_waiting_has_no_cleanup_policy_key() -> None:
    assert cleanup_policy_key_for_outcome(FailedImportOutcome.PENDING_WAITING) is None


def test_unknown_has_no_cleanup_policy_key() -> None:
    assert cleanup_policy_key_for_outcome(FailedImportOutcome.UNKNOWN) is None


def test_pending_waiting_never_enables_cleanup_with_default_policy() -> None:
    p = default_failed_import_cleanup_policy()
    assert is_failed_import_cleanup_enabled(FailedImportOutcome.PENDING_WAITING, p) is False


def test_unknown_never_enables_cleanup_with_default_policy() -> None:
    p = default_failed_import_cleanup_policy()
    assert is_failed_import_cleanup_enabled(FailedImportOutcome.UNKNOWN, p) is False


def test_pending_waiting_never_enables_cleanup_even_if_all_toggles_on() -> None:
    """Non-terminal outcomes do not gain cleanup eligibility from other toggles."""
    p = FailedImportCleanupPolicy(
        remove_quality_rejections=True,
        remove_unmatched_manual_import_rejections=True,
        remove_corrupt_imports=True,
        remove_failed_downloads=True,
        remove_failed_imports=True,
    )
    assert is_failed_import_cleanup_enabled(FailedImportOutcome.PENDING_WAITING, p) is False
    assert is_failed_import_cleanup_enabled(FailedImportOutcome.UNKNOWN, p) is False


def test_default_policy_disables_all_terminal_cleanup() -> None:
    p = default_failed_import_cleanup_policy()
    for o in (
        FailedImportOutcome.QUALITY,
        FailedImportOutcome.UNMATCHED,
        FailedImportOutcome.CORRUPT,
        FailedImportOutcome.DOWNLOAD_FAILED,
        FailedImportOutcome.IMPORT_FAILED,
    ):
        assert is_failed_import_cleanup_enabled(o, p) is False


def test_only_matching_toggle_enables_cleanup_for_that_outcome() -> None:
    p = FailedImportCleanupPolicy(remove_corrupt_imports=True)
    assert is_failed_import_cleanup_enabled(FailedImportOutcome.CORRUPT, p) is True
    assert is_failed_import_cleanup_enabled(FailedImportOutcome.QUALITY, p) is False
    assert is_failed_import_cleanup_enabled(FailedImportOutcome.UNMATCHED, p) is False
