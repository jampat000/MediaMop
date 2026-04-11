"""Thin routing for failed import cleanup planning — dispatches to app-specific planners.

Explicit :class:`FailedImportArrApp` boundary only (no payload sniffing). Returns the concrete
Radarr or Sonarr plan type unchanged; no shared executor or merged result blob.
"""

from __future__ import annotations

from enum import Enum

from mediamop.modules.arr_failed_import.policy import FailedImportCleanupPolicy
from mediamop.modules.fetcher.radarr_failed_import_cleanup import (
    RadarrFailedImportCleanupPlan,
    plan_radarr_failed_import_cleanup,
)
from mediamop.modules.fetcher.sonarr_failed_import_cleanup import (
    SonarrFailedImportCleanupPlan,
    plan_sonarr_failed_import_cleanup,
)


class FailedImportArrApp(str, Enum):
    """Upstream *arr product boundary for cleanup planning dispatch."""

    RADARR = "radarr"
    SONARR = "sonarr"


FailedImportCleanupPlanningResult = RadarrFailedImportCleanupPlan | SonarrFailedImportCleanupPlan


def parse_failed_import_arr_app(raw: str) -> FailedImportArrApp:
    """Parse a user- or config-supplied app label; raises ``ValueError`` if unknown."""
    key = raw.strip().lower()
    if key == FailedImportArrApp.RADARR.value:
        return FailedImportArrApp.RADARR
    if key == FailedImportArrApp.SONARR.value:
        return FailedImportArrApp.SONARR
    raise ValueError(f"unknown failed-import arr app: {raw!r}")


def plan_failed_import_cleanup(
    app: FailedImportArrApp,
    *,
    status_message_blob: str,
    policy: FailedImportCleanupPolicy,
    queue_item_id: int | None = None,
) -> FailedImportCleanupPlanningResult:
    """Route cleanup planning to the Radarr or Sonarr seam; no HTTP or deletes.

    ``queue_item_id`` is passed through as ``radarr_queue_item_id`` or
    ``sonarr_queue_item_id`` on the returned plan.
    """
    if app == FailedImportArrApp.RADARR:
        return plan_radarr_failed_import_cleanup(
            status_message_blob=status_message_blob,
            policy=policy,
            radarr_queue_item_id=queue_item_id,
        )
    if app == FailedImportArrApp.SONARR:
        return plan_sonarr_failed_import_cleanup(
            status_message_blob=status_message_blob,
            policy=policy,
            sonarr_queue_item_id=queue_item_id,
        )
    raise AssertionError(f"unhandled FailedImportArrApp: {app!r}")
