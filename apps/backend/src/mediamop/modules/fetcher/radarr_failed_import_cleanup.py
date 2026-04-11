"""Radarr-only failed import cleanup planning — consumes the shared eligibility decision.

No Sonarr logic here. No HTTP or queue mutation: maps policy + Radarr status text to a
plan a future Radarr client could execute (e.g. remove item from download queue).

The domain seam :func:`decide_failed_import_cleanup_eligibility` is always used; this
module does not reclassify or reapply policy rules.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from mediamop.modules.arr_failed_import.decision import (
    FailedImportCleanupEligibilityDecision,
    decide_failed_import_cleanup_eligibility,
)
from mediamop.modules.arr_failed_import.policy import FailedImportCleanupPolicy


class RadarrFailedImportCleanupAction(str, Enum):
    """What a future Radarr executor would do — planning only in this pass."""

    NONE = "none"
    PLANNED_REMOVE_FROM_DOWNLOAD_QUEUE = "planned_remove_from_download_queue"


@dataclass(frozen=True, slots=True)
class RadarrFailedImportCleanupPlan:
    """Radarr-scoped cleanup plan derived from the pure eligibility decision."""

    decision: FailedImportCleanupEligibilityDecision
    action: RadarrFailedImportCleanupAction
    radarr_queue_item_id: int | None = None


def plan_radarr_failed_import_cleanup(
    *,
    status_message_blob: str,
    policy: FailedImportCleanupPolicy,
    radarr_queue_item_id: int | None = None,
) -> RadarrFailedImportCleanupPlan:
    """Build a cleanup plan from Radarr-style status message text and policy.

    ``status_message_blob`` should be the concatenated (or representative) status /
    failure messages from the Radarr queue item, as the classifier expects.

    When ``decision.cleanup_eligible`` is True, ``action`` is
    :attr:`RadarrFailedImportCleanupAction.PLANNED_REMOVE_FROM_DOWNLOAD_QUEUE`;
    otherwise :attr:`RadarrFailedImportCleanupAction.NONE`. No API calls are made.
    """
    decision = decide_failed_import_cleanup_eligibility(status_message_blob, policy)
    action = (
        RadarrFailedImportCleanupAction.PLANNED_REMOVE_FROM_DOWNLOAD_QUEUE
        if decision.cleanup_eligible
        else RadarrFailedImportCleanupAction.NONE
    )
    return RadarrFailedImportCleanupPlan(
        decision=decision,
        action=action,
        radarr_queue_item_id=radarr_queue_item_id,
    )
