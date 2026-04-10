"""Refiner Pass 10: Radarr failed import cleanup execution (plan → client, Radarr-only)."""

from __future__ import annotations

from dataclasses import dataclass

from mediamop.modules.refiner.failed_import_classification import FailedImportOutcome
from mediamop.modules.refiner.failed_import_cleanup_decision import (
    FailedImportCleanupEligibilityDecision,
    FailedImportCleanupEligibilityReason,
)
from mediamop.modules.refiner.failed_import_cleanup_policy import FailedImportCleanupPolicyKey
from mediamop.modules.refiner.radarr_cleanup_execution import (
    RadarrFailedImportCleanupExecutionOutcome,
    execute_radarr_failed_import_cleanup_plan,
)
from mediamop.modules.refiner.failed_import_cleanup_policy import FailedImportCleanupPolicy
from mediamop.modules.refiner.radarr_failed_import_cleanup import (
    RadarrFailedImportCleanupAction,
    RadarrFailedImportCleanupPlan,
    plan_radarr_failed_import_cleanup,
)


@dataclass
class _RecordingRadarrClient:
    calls: list[int]

    def __init__(self) -> None:
        self.calls = []

    def remove_queue_item(self, queue_item_id: int) -> None:
        self.calls.append(queue_item_id)


def test_none_plan_performs_no_client_action() -> None:
    d = FailedImportCleanupEligibilityDecision(
        outcome=FailedImportOutcome.PENDING_WAITING,
        policy_key=None,
        cleanup_eligible=False,
        reason=FailedImportCleanupEligibilityReason.INELIGIBLE_NO_CLEANUP_POLICY_KEY,
    )
    plan = RadarrFailedImportCleanupPlan(
        decision=d,
        action=RadarrFailedImportCleanupAction.NONE,
        radarr_queue_item_id=42,
    )
    client = _RecordingRadarrClient()
    out = execute_radarr_failed_import_cleanup_plan(plan, client)
    assert out is RadarrFailedImportCleanupExecutionOutcome.NO_OP
    assert client.calls == []


def test_planned_remove_with_queue_id_calls_client_once() -> None:
    d = FailedImportCleanupEligibilityDecision(
        outcome=FailedImportOutcome.IMPORT_FAILED,
        policy_key=FailedImportCleanupPolicyKey.REMOVE_FAILED_IMPORTS,
        cleanup_eligible=True,
        reason=FailedImportCleanupEligibilityReason.ELIGIBLE,
    )
    plan = RadarrFailedImportCleanupPlan(
        decision=d,
        action=RadarrFailedImportCleanupAction.PLANNED_REMOVE_FROM_DOWNLOAD_QUEUE,
        radarr_queue_item_id=77,
    )
    client = _RecordingRadarrClient()
    out = execute_radarr_failed_import_cleanup_plan(plan, client)
    assert out is RadarrFailedImportCleanupExecutionOutcome.REMOVED_QUEUE_ITEM
    assert client.calls == [77]


def test_planned_remove_missing_queue_id_skips_client_safely() -> None:
    d = FailedImportCleanupEligibilityDecision(
        outcome=FailedImportOutcome.CORRUPT,
        policy_key=FailedImportCleanupPolicyKey.REMOVE_CORRUPT_IMPORTS,
        cleanup_eligible=True,
        reason=FailedImportCleanupEligibilityReason.ELIGIBLE,
    )
    plan = RadarrFailedImportCleanupPlan(
        decision=d,
        action=RadarrFailedImportCleanupAction.PLANNED_REMOVE_FROM_DOWNLOAD_QUEUE,
        radarr_queue_item_id=None,
    )
    client = _RecordingRadarrClient()
    out = execute_radarr_failed_import_cleanup_plan(plan, client)
    assert out is RadarrFailedImportCleanupExecutionOutcome.SKIPPED_MISSING_QUEUE_ITEM_ID
    assert client.calls == []


def test_planner_produced_plan_round_trips_through_executor_without_replanning() -> None:
    """Contract: execution consumes the planning seam output as-is (id + action)."""
    plan = plan_radarr_failed_import_cleanup(
        status_message_blob="Import failed",
        policy=FailedImportCleanupPolicy(remove_failed_imports=True),
        radarr_queue_item_id=888,
    )
    client = _RecordingRadarrClient()
    out = execute_radarr_failed_import_cleanup_plan(plan, client)
    assert out is RadarrFailedImportCleanupExecutionOutcome.REMOVED_QUEUE_ITEM
    assert client.calls == [888]
