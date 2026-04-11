"""Sonarr failed import cleanup planning seam (Sonarr-only, no executor)."""

from __future__ import annotations

from mediamop.modules.arr_failed_import.decision import decide_failed_import_cleanup_eligibility
from mediamop.modules.arr_failed_import.policy import (
    FailedImportCleanupPolicy,
    FailedImportCleanupPolicyKey,
    default_failed_import_cleanup_policy,
)
from mediamop.modules.fetcher.sonarr_failed_import_cleanup import (
    SonarrFailedImportCleanupAction,
    SonarrFailedImportCleanupPlan,
    plan_sonarr_failed_import_cleanup,
)


def _policy_only(key: FailedImportCleanupPolicyKey, on: bool) -> FailedImportCleanupPolicy:
    return FailedImportCleanupPolicy(
        remove_quality_rejections=(key is FailedImportCleanupPolicyKey.REMOVE_QUALITY_REJECTIONS and on),
        remove_unmatched_manual_import_rejections=(
            key is FailedImportCleanupPolicyKey.REMOVE_UNMATCHED_MANUAL_IMPORT_REJECTIONS and on
        ),
        remove_corrupt_imports=(key is FailedImportCleanupPolicyKey.REMOVE_CORRUPT_IMPORTS and on),
        remove_failed_downloads=(key is FailedImportCleanupPolicyKey.REMOVE_FAILED_DOWNLOADS and on),
        remove_failed_imports=(key is FailedImportCleanupPolicyKey.REMOVE_FAILED_IMPORTS and on),
    )


def test_sonarr_terminal_failure_toggle_off_plans_no_action() -> None:
    policy = _policy_only(FailedImportCleanupPolicyKey.REMOVE_FAILED_IMPORTS, on=False)
    plan = plan_sonarr_failed_import_cleanup(
        status_message_blob="Import failed",
        policy=policy,
        sonarr_queue_item_id=202,
    )
    assert plan.action == SonarrFailedImportCleanupAction.NONE
    assert plan.decision.cleanup_eligible is False
    assert plan.sonarr_queue_item_id == 202


def test_sonarr_terminal_failure_matching_toggle_on_plans_queue_removal() -> None:
    policy = _policy_only(FailedImportCleanupPolicyKey.REMOVE_FAILED_IMPORTS, on=True)
    plan = plan_sonarr_failed_import_cleanup(
        status_message_blob="Import failed",
        policy=policy,
    )
    assert plan.action == SonarrFailedImportCleanupAction.PLANNED_REMOVE_FROM_DOWNLOAD_QUEUE
    assert plan.decision.cleanup_eligible is True


def test_sonarr_pending_waiting_never_plans_removal() -> None:
    policy = FailedImportCleanupPolicy(
        remove_quality_rejections=True,
        remove_unmatched_manual_import_rejections=True,
        remove_corrupt_imports=True,
        remove_failed_downloads=True,
        remove_failed_imports=True,
    )
    plan = plan_sonarr_failed_import_cleanup(
        status_message_blob="Downloaded - Waiting to Import",
        policy=policy,
    )
    assert plan.action == SonarrFailedImportCleanupAction.NONE
    assert plan.decision.cleanup_eligible is False


def test_sonarr_unknown_never_plans_removal() -> None:
    plan = plan_sonarr_failed_import_cleanup(
        status_message_blob="Something odd from Sonarr.",
        policy=_policy_only(FailedImportCleanupPolicyKey.REMOVE_CORRUPT_IMPORTS, on=True),
    )
    assert plan.action == SonarrFailedImportCleanupAction.NONE


def test_sonarr_blob_waiting_plus_terminal_precedence_then_policy() -> None:
    blob = "Downloaded - Waiting to Import. Manual Import required."
    plan_off = plan_sonarr_failed_import_cleanup(status_message_blob=blob, policy=default_failed_import_cleanup_policy())
    assert plan_off.decision.cleanup_eligible is False
    assert plan_off.action == SonarrFailedImportCleanupAction.NONE

    plan_on = plan_sonarr_failed_import_cleanup(
        status_message_blob=blob,
        policy=_policy_only(FailedImportCleanupPolicyKey.REMOVE_UNMATCHED_MANUAL_IMPORT_REJECTIONS, on=True),
    )
    assert plan_on.decision.cleanup_eligible is True
    assert plan_on.action == SonarrFailedImportCleanupAction.PLANNED_REMOVE_FROM_DOWNLOAD_QUEUE


def test_sonarr_plan_decision_matches_pure_decision_seam() -> None:
    blob = "Not an upgrade for existing movie file"
    policy = _policy_only(FailedImportCleanupPolicyKey.REMOVE_QUALITY_REJECTIONS, on=True)
    expected = decide_failed_import_cleanup_eligibility(blob, policy)
    plan = plan_sonarr_failed_import_cleanup(status_message_blob=blob, policy=policy)
    assert plan.decision == expected


def test_sonarr_failed_import_cleanup_types_are_sonarr_named_not_shared_executor() -> None:
    assert "Sonarr" in SonarrFailedImportCleanupPlan.__name__
    assert "Sonarr" in SonarrFailedImportCleanupAction.__name__
