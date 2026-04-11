"""Cleanup toggle contract for :class:`~mediamop.modules.arr_failed_import.classification.FailedImportOutcome`.

Each terminal classifier outcome maps to exactly one policy field. There is no shared
“cleanup everything” bucket. :attr:`FailedImportOutcome.PENDING_WAITING` and
:attr:`FailedImportOutcome.UNKNOWN` never select a cleanup policy key by default.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Final

from mediamop.modules.arr_failed_import.classification import FailedImportOutcome


class FailedImportCleanupPolicyKey(str, Enum):
    """Stable keys for persisted or API-facing toggles — 1:1 with terminal outcomes only."""

    REMOVE_QUALITY_REJECTIONS = "remove_quality_rejections"
    REMOVE_UNMATCHED_MANUAL_IMPORT_REJECTIONS = "remove_unmatched_manual_import_rejections"
    REMOVE_CORRUPT_IMPORTS = "remove_corrupt_imports"
    REMOVE_FAILED_DOWNLOADS = "remove_failed_downloads"
    REMOVE_FAILED_IMPORTS = "remove_failed_imports"


_TERMINAL_OUTCOME_TO_KEY: Final[dict[FailedImportOutcome, FailedImportCleanupPolicyKey]] = {
    FailedImportOutcome.QUALITY: FailedImportCleanupPolicyKey.REMOVE_QUALITY_REJECTIONS,
    FailedImportOutcome.UNMATCHED: FailedImportCleanupPolicyKey.REMOVE_UNMATCHED_MANUAL_IMPORT_REJECTIONS,
    FailedImportOutcome.CORRUPT: FailedImportCleanupPolicyKey.REMOVE_CORRUPT_IMPORTS,
    FailedImportOutcome.DOWNLOAD_FAILED: FailedImportCleanupPolicyKey.REMOVE_FAILED_DOWNLOADS,
    FailedImportOutcome.IMPORT_FAILED: FailedImportCleanupPolicyKey.REMOVE_FAILED_IMPORTS,
}


@dataclass(frozen=True, slots=True)
class FailedImportCleanupPolicy:
    """Per-outcome cleanup opt-in. Defaults are conservative (no destructive cleanup)."""

    remove_quality_rejections: bool = False
    remove_unmatched_manual_import_rejections: bool = False
    remove_corrupt_imports: bool = False
    remove_failed_downloads: bool = False
    remove_failed_imports: bool = False

    def value_for_key(self, key: FailedImportCleanupPolicyKey) -> bool:
        if key is FailedImportCleanupPolicyKey.REMOVE_QUALITY_REJECTIONS:
            return self.remove_quality_rejections
        if key is FailedImportCleanupPolicyKey.REMOVE_UNMATCHED_MANUAL_IMPORT_REJECTIONS:
            return self.remove_unmatched_manual_import_rejections
        if key is FailedImportCleanupPolicyKey.REMOVE_CORRUPT_IMPORTS:
            return self.remove_corrupt_imports
        if key is FailedImportCleanupPolicyKey.REMOVE_FAILED_DOWNLOADS:
            return self.remove_failed_downloads
        return self.remove_failed_imports


def default_failed_import_cleanup_policy() -> FailedImportCleanupPolicy:
    """All cleanup toggles off until explicitly enabled."""
    return FailedImportCleanupPolicy()


def cleanup_policy_key_for_outcome(outcome: FailedImportOutcome) -> FailedImportCleanupPolicyKey | None:
    """Map a classifier outcome to its cleanup toggle key, or None if not a terminal cleanup case."""
    return _TERMINAL_OUTCOME_TO_KEY.get(outcome)


def is_failed_import_cleanup_enabled(
    outcome: FailedImportOutcome,
    policy: FailedImportCleanupPolicy,
) -> bool:
    """True only when the outcome has a dedicated policy slot and that toggle is on.

    :attr:`FailedImportOutcome.PENDING_WAITING` and :attr:`FailedImportOutcome.UNKNOWN`
    always yield False here (not destructive cleanup targets by default).
    """
    key = cleanup_policy_key_for_outcome(outcome)
    if key is None:
        return False
    return policy.value_for_key(key)
