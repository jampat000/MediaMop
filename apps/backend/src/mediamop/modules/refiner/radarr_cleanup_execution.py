"""Radarr-only failed import cleanup execution — consumes :class:`RadarrFailedImportCleanupPlan`.

Does not reclassify or re-evaluate policy; only interprets ``plan.action`` and
``plan.radarr_queue_item_id``. Inject a :class:`RadarrQueueOperations` implementation
(HTTP or mock) at the boundary.
"""

from __future__ import annotations

import urllib.error
import urllib.request
from enum import Enum
from typing import Protocol

from mediamop.modules.refiner.radarr_failed_import_cleanup import (
    RadarrFailedImportCleanupAction,
    RadarrFailedImportCleanupPlan,
)


class RadarrQueueOperations(Protocol):
    """Narrow Radarr queue API surface for cleanup execution (easy to fake in tests)."""

    def remove_queue_item(self, queue_item_id: int) -> None:
        """Delete one queue row (Radarr v3 ``DELETE /api/v3/queue/{id}``)."""
        ...


class RadarrFailedImportCleanupExecutionOutcome(str, Enum):
    """Result of attempting to apply a plan — no Sonarr outcomes here."""

    NO_OP = "no_op"
    REMOVED_QUEUE_ITEM = "removed_queue_item"
    SKIPPED_MISSING_QUEUE_ITEM_ID = "skipped_missing_queue_item_id"


def execute_radarr_failed_import_cleanup_plan(
    plan: RadarrFailedImportCleanupPlan,
    queue_client: RadarrQueueOperations,
) -> RadarrFailedImportCleanupExecutionOutcome:
    """Apply ``plan`` using ``queue_client`` when a remove is planned and an id exists.

    - :attr:`RadarrFailedImportCleanupAction.NONE` → :attr:`RadarrFailedImportCleanupExecutionOutcome.NO_OP` (no client call).
    - Planned remove without ``radarr_queue_item_id`` → :attr:`RadarrFailedImportCleanupExecutionOutcome.SKIPPED_MISSING_QUEUE_ITEM_ID`.
    - Planned remove with id → ``queue_client.remove_queue_item(id)`` then :attr:`RadarrFailedImportCleanupExecutionOutcome.REMOVED_QUEUE_ITEM`.
    """
    if plan.action is RadarrFailedImportCleanupAction.NONE:
        return RadarrFailedImportCleanupExecutionOutcome.NO_OP
    if plan.action is not RadarrFailedImportCleanupAction.PLANNED_REMOVE_FROM_DOWNLOAD_QUEUE:
        raise AssertionError(f"unhandled RadarrFailedImportCleanupAction: {plan.action!r}")
    if plan.radarr_queue_item_id is None:
        return RadarrFailedImportCleanupExecutionOutcome.SKIPPED_MISSING_QUEUE_ITEM_ID
    queue_client.remove_queue_item(plan.radarr_queue_item_id)
    return RadarrFailedImportCleanupExecutionOutcome.REMOVED_QUEUE_ITEM


class RadarrQueueHttpClient:
    """Minimal stdlib HTTP client: ``DELETE {base}/api/v3/queue/{id}`` with ``X-Api-Key``."""

    def __init__(self, base_url: str, api_key: str, *, timeout_seconds: float = 30.0) -> None:
        self._base = base_url.rstrip("/")
        self._api_key = api_key
        self._timeout = timeout_seconds

    def remove_queue_item(self, queue_item_id: int) -> None:
        url = f"{self._base}/api/v3/queue/{queue_item_id}"
        req = urllib.request.Request(
            url,
            method="DELETE",
            headers={"X-Api-Key": self._api_key},
        )
        try:
            with urllib.request.urlopen(req, timeout=self._timeout) as resp:
                if resp.status not in (200, 204):
                    raise RuntimeError(
                        f"Radarr queue delete unexpected status {resp.status} for {url!r}",
                    )
        except urllib.error.HTTPError as e:
            raise RuntimeError(
                f"Radarr queue delete failed: HTTP {e.code} for {url!r}",
            ) from e
