"""Pure eligibility decision: failed-import message blob + cleanup policy → no side effects.

Composes :func:`~mediamop.modules.arr_failed_import.classification.classify_failed_import_message`
with :func:`~mediamop.modules.arr_failed_import.policy.cleanup_policy_key_for_outcome`
and policy toggles. Does not delete, mutate queues, or call *arr APIs.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from mediamop.modules.arr_failed_import.classification import (
    FailedImportOutcome,
    classify_failed_import_message,
)
from mediamop.modules.arr_failed_import.policy import (
    FailedImportCleanupPolicy,
    FailedImportCleanupPolicyKey,
    cleanup_policy_key_for_outcome,
    is_failed_import_cleanup_enabled,
)


class FailedImportCleanupEligibilityReason(str, Enum):
    """Why ``cleanup_eligible`` is true or false — stable for logs/UI later."""

    ELIGIBLE = "eligible"
    INELIGIBLE_NO_CLEANUP_POLICY_KEY = "ineligible_no_cleanup_policy_key"
    INELIGIBLE_POLICY_TOGGLE_DISABLED = "ineligible_policy_toggle_disabled"


@dataclass(frozen=True, slots=True)
class FailedImportCleanupEligibilityDecision:
    """Result of applying classification + policy to one message blob."""

    outcome: FailedImportOutcome
    policy_key: FailedImportCleanupPolicyKey | None
    cleanup_eligible: bool
    reason: FailedImportCleanupEligibilityReason


def decide_failed_import_cleanup_eligibility(
    message_blob: str,
    policy: FailedImportCleanupPolicy,
) -> FailedImportCleanupEligibilityDecision:
    """Classify ``message_blob`` and decide whether cleanup is allowed for this policy.

    Terminal outcomes are eligible only when their 1:1 toggle is enabled.
    :attr:`FailedImportOutcome.PENDING_WAITING` and :attr:`FailedImportOutcome.UNKNOWN`
    never yield a policy key and are never eligible.
    """
    outcome = classify_failed_import_message(message_blob)
    policy_key = cleanup_policy_key_for_outcome(outcome)
    cleanup_eligible = is_failed_import_cleanup_enabled(outcome, policy)

    if policy_key is None:
        reason = FailedImportCleanupEligibilityReason.INELIGIBLE_NO_CLEANUP_POLICY_KEY
    elif cleanup_eligible:
        reason = FailedImportCleanupEligibilityReason.ELIGIBLE
    else:
        reason = FailedImportCleanupEligibilityReason.INELIGIBLE_POLICY_TOGGLE_DISABLED

    return FailedImportCleanupEligibilityDecision(
        outcome=outcome,
        policy_key=policy_key,
        cleanup_eligible=cleanup_eligible,
        reason=reason,
    )
