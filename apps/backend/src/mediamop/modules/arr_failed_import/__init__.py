"""Shared *arr download-queue failed-import rules (classification, policy, env toggles).

Neutral between Refiner and Fetcher so neither module imports the other for this domain.
Fetcher owns ``fetcher_jobs`` orchestration and the operator HTTP surfaces for failed-import drives;
Refiner may consume these rules via narrow ports without owning the Fetcher job table.
"""

from __future__ import annotations

from mediamop.modules.arr_failed_import.classification import (
    FailedImportOutcome,
    classify_failed_import_message,
    normalize_failed_import_blob,
)
from mediamop.modules.arr_failed_import.decision import (
    FailedImportCleanupEligibilityDecision,
    FailedImportCleanupEligibilityReason,
    decide_failed_import_cleanup_eligibility,
)
from mediamop.modules.arr_failed_import.env_settings import (
    AppFailedImportCleanupPolicySettings,
    FailedImportCleanupSettingsBundle,
    default_failed_import_cleanup_settings_bundle,
    load_failed_import_cleanup_settings_bundle,
)
from mediamop.modules.arr_failed_import.policy import (
    FailedImportCleanupPolicy,
    FailedImportCleanupPolicyKey,
    cleanup_policy_key_for_outcome,
    default_failed_import_cleanup_policy,
    is_failed_import_cleanup_enabled,
)

__all__ = [
    "AppFailedImportCleanupPolicySettings",
    "FailedImportCleanupEligibilityDecision",
    "FailedImportCleanupEligibilityReason",
    "FailedImportCleanupPolicy",
    "FailedImportCleanupPolicyKey",
    "FailedImportCleanupSettingsBundle",
    "FailedImportOutcome",
    "classify_failed_import_message",
    "cleanup_policy_key_for_outcome",
    "decide_failed_import_cleanup_eligibility",
    "default_failed_import_cleanup_policy",
    "default_failed_import_cleanup_settings_bundle",
    "is_failed_import_cleanup_enabled",
    "load_failed_import_cleanup_settings_bundle",
    "normalize_failed_import_blob",
]
