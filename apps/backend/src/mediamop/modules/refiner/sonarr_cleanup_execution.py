"""Sonarr-only failed import cleanup execution — consumes :class:`SonarrFailedImportCleanupPlan`.

Does not reclassify or re-evaluate policy; only interprets ``plan.action`` and
``plan.sonarr_queue_item_id``. Inject a :class:`SonarrQueueOperations` implementation
(HTTP or mock) at the boundary.
"""

from __future__ import annotations

import urllib.error
import urllib.request
from enum import Enum
from typing import Protocol

from mediamop.modules.refiner.sonarr_failed_import_cleanup import (
    SonarrFailedImportCleanupAction,
    SonarrFailedImportCleanupPlan,
)


class SonarrQueueOperations(Protocol):
    """Narrow Sonarr queue API surface for cleanup execution (easy to fake in tests)."""

    def remove_queue_item(self, queue_item_id: int) -> None:
        """Delete one queue row (Sonarr v3 ``DELETE /api/v3/queue/{id}``)."""
        ...


class SonarrFailedImportCleanupExecutionOutcome(str, Enum):
    """Result of attempting to apply a plan — no Radarr outcomes here."""

    NO_OP = "no_op"
    REMOVED_QUEUE_ITEM = "removed_queue_item"
    SKIPPED_MISSING_QUEUE_ITEM_ID = "skipped_missing_queue_item_id"


def execute_sonarr_failed_import_cleanup_plan(
    plan: SonarrFailedImportCleanupPlan,
    queue_client: SonarrQueueOperations,
) -> SonarrFailedImportCleanupExecutionOutcome:
    """Apply ``plan`` using ``queue_client`` when a remove is planned and an id exists.

    - :attr:`SonarrFailedImportCleanupAction.NONE` → :attr:`SonarrFailedImportCleanupExecutionOutcome.NO_OP` (no client call).
    - Planned remove without ``sonarr_queue_item_id`` → :attr:`SonarrFailedImportCleanupExecutionOutcome.SKIPPED_MISSING_QUEUE_ITEM_ID`.
    - Planned remove with id → ``queue_client.remove_queue_item(id)`` then :attr:`SonarrFailedImportCleanupExecutionOutcome.REMOVED_QUEUE_ITEM`.
    """
    if plan.action is SonarrFailedImportCleanupAction.NONE:
        return SonarrFailedImportCleanupExecutionOutcome.NO_OP
    if plan.action is not SonarrFailedImportCleanupAction.PLANNED_REMOVE_FROM_DOWNLOAD_QUEUE:
        raise AssertionError(f"unhandled SonarrFailedImportCleanupAction: {plan.action!r}")
    if plan.sonarr_queue_item_id is None:
        return SonarrFailedImportCleanupExecutionOutcome.SKIPPED_MISSING_QUEUE_ITEM_ID
    queue_client.remove_queue_item(plan.sonarr_queue_item_id)
    return SonarrFailedImportCleanupExecutionOutcome.REMOVED_QUEUE_ITEM


class SonarrQueueHttpClient:
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
                        f"Sonarr queue delete unexpected status {resp.status} for {url!r}",
                    )
        except urllib.error.HTTPError as e:
            raise RuntimeError(
                f"Sonarr queue delete failed: HTTP {e.code} for {url!r}",
            ) from e
