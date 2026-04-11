"""Pure failed-import cleanup eligibility decision (no execution)."""

from __future__ import annotations

import pytest

from mediamop.modules.arr_failed_import.classification import FailedImportOutcome
from mediamop.modules.arr_failed_import.decision import (
    FailedImportCleanupEligibilityDecision,
    FailedImportCleanupEligibilityReason,
    decide_failed_import_cleanup_eligibility,
)
from mediamop.modules.arr_failed_import.policy import (
    FailedImportCleanupPolicy,
    FailedImportCleanupPolicyKey,
    default_failed_import_cleanup_policy,
)


def _policy_with_only(key: FailedImportCleanupPolicyKey, enabled: bool) -> FailedImportCleanupPolicy:
    return FailedImportCleanupPolicy(
        remove_quality_rejections=(key is FailedImportCleanupPolicyKey.REMOVE_QUALITY_REJECTIONS and enabled),
        remove_unmatched_manual_import_rejections=(
            key is FailedImportCleanupPolicyKey.REMOVE_UNMATCHED_MANUAL_IMPORT_REJECTIONS and enabled
        ),
        remove_corrupt_imports=(key is FailedImportCleanupPolicyKey.REMOVE_CORRUPT_IMPORTS and enabled),
        remove_failed_downloads=(key is FailedImportCleanupPolicyKey.REMOVE_FAILED_DOWNLOADS and enabled),
        remove_failed_imports=(key is FailedImportCleanupPolicyKey.REMOVE_FAILED_IMPORTS and enabled),
    )


_TERMINAL_BLOBS: tuple[tuple[str, FailedImportOutcome, FailedImportCleanupPolicyKey], ...] = (
    ("Not an upgrade for existing movie file", FailedImportOutcome.QUALITY, FailedImportCleanupPolicyKey.REMOVE_QUALITY_REJECTIONS),
    ("Manual Import required", FailedImportOutcome.UNMATCHED, FailedImportCleanupPolicyKey.REMOVE_UNMATCHED_MANUAL_IMPORT_REJECTIONS),
    ("file is corrupt", FailedImportOutcome.CORRUPT, FailedImportCleanupPolicyKey.REMOVE_CORRUPT_IMPORTS),
    ("Download failed", FailedImportOutcome.DOWNLOAD_FAILED, FailedImportCleanupPolicyKey.REMOVE_FAILED_DOWNLOADS),
    ("Import failed", FailedImportOutcome.IMPORT_FAILED, FailedImportCleanupPolicyKey.REMOVE_FAILED_IMPORTS),
)


@pytest.mark.parametrize("blob,outcome,key", _TERMINAL_BLOBS)
def test_terminal_outcome_not_cleanup_eligible_when_matching_toggle_disabled(
    blob: str,
    outcome: FailedImportOutcome,
    key: FailedImportCleanupPolicyKey,
) -> None:
    policy = _policy_with_only(key, enabled=False)
    d = decide_failed_import_cleanup_eligibility(blob, policy)
    assert d.outcome == outcome
    assert d.policy_key == key
    assert d.cleanup_eligible is False
    assert d.reason == FailedImportCleanupEligibilityReason.INELIGIBLE_POLICY_TOGGLE_DISABLED


@pytest.mark.parametrize("blob,outcome,key", _TERMINAL_BLOBS)
def test_terminal_outcome_cleanup_eligible_when_only_matching_toggle_enabled(
    blob: str,
    outcome: FailedImportOutcome,
    key: FailedImportCleanupPolicyKey,
) -> None:
    policy = _policy_with_only(key, enabled=True)
    d = decide_failed_import_cleanup_eligibility(blob, policy)
    assert d.outcome == outcome
    assert d.policy_key == key
    assert d.cleanup_eligible is True
    assert d.reason == FailedImportCleanupEligibilityReason.ELIGIBLE


def test_pending_waiting_never_cleanup_eligible_even_if_all_toggles_on() -> None:
    policy = FailedImportCleanupPolicy(
        remove_quality_rejections=True,
        remove_unmatched_manual_import_rejections=True,
        remove_corrupt_imports=True,
        remove_failed_downloads=True,
        remove_failed_imports=True,
    )
    d = decide_failed_import_cleanup_eligibility("Downloaded - Waiting to Import", policy)
    assert d.outcome == FailedImportOutcome.PENDING_WAITING
    assert d.policy_key is None
    assert d.cleanup_eligible is False
    assert d.reason == FailedImportCleanupEligibilityReason.INELIGIBLE_NO_CLEANUP_POLICY_KEY


def test_unknown_never_cleanup_eligible() -> None:
    policy = FailedImportCleanupPolicy(remove_corrupt_imports=True)
    d = decide_failed_import_cleanup_eligibility("Unrecognized status text.", policy)
    assert d.outcome == FailedImportOutcome.UNKNOWN
    assert d.policy_key is None
    assert d.cleanup_eligible is False
    assert d.reason == FailedImportCleanupEligibilityReason.INELIGIBLE_NO_CLEANUP_POLICY_KEY


def test_blob_with_waiting_and_terminal_classifies_terminal_then_policy_applies() -> None:
    """Classifier precedence: terminal beats waiting; decision uses that outcome + policy."""
    blob = "Downloaded - Waiting to Import. Manual Import required."
    policy_off = default_failed_import_cleanup_policy()
    d_off = decide_failed_import_cleanup_eligibility(blob, policy_off)
    assert d_off.outcome == FailedImportOutcome.UNMATCHED
    assert d_off.policy_key == FailedImportCleanupPolicyKey.REMOVE_UNMATCHED_MANUAL_IMPORT_REJECTIONS
    assert d_off.cleanup_eligible is False
    assert d_off.reason == FailedImportCleanupEligibilityReason.INELIGIBLE_POLICY_TOGGLE_DISABLED

    policy_on = _policy_with_only(
        FailedImportCleanupPolicyKey.REMOVE_UNMATCHED_MANUAL_IMPORT_REJECTIONS,
        enabled=True,
    )
    d_on = decide_failed_import_cleanup_eligibility(blob, policy_on)
    assert d_on.outcome == FailedImportOutcome.UNMATCHED
    assert d_on.cleanup_eligible is True
    assert d_on.reason == FailedImportCleanupEligibilityReason.ELIGIBLE


def test_decision_is_frozen_dataclass_for_stable_shape() -> None:
    d = decide_failed_import_cleanup_eligibility("Import failed", default_failed_import_cleanup_policy())
    assert isinstance(d, FailedImportCleanupEligibilityDecision)
