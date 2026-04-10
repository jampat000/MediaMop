"""Thin routing for failed import cleanup planning — dispatches to app-specific planners.

Explicit :class:`RefinerArrApp` boundary only (no payload sniffing). Returns the concrete
Radarr or Sonarr plan type unchanged; no shared executor or merged result blob.
"""

from __future__ import annotations

from enum import Enum

from mediamop.modules.refiner.failed_import_cleanup_policy import FailedImportCleanupPolicy
from mediamop.modules.refiner.radarr_failed_import_cleanup import (
    RadarrFailedImportCleanupPlan,
    plan_radarr_failed_import_cleanup,
)
from mediamop.modules.refiner.sonarr_failed_import_cleanup import (
    SonarrFailedImportCleanupPlan,
    plan_sonarr_failed_import_cleanup,
)


class RefinerArrApp(str, Enum):
    """Upstream *arr product boundary for cleanup planning dispatch."""

    RADARR = "radarr"
    SONARR = "sonarr"


FailedImportCleanupPlanningResult = RadarrFailedImportCleanupPlan | SonarrFailedImportCleanupPlan


def parse_refiner_arr_app(raw: str) -> RefinerArrApp:
    """Parse a user- or config-supplied app label; raises ``ValueError`` if unknown."""
    key = raw.strip().lower()
    if key == RefinerArrApp.RADARR.value:
        return RefinerArrApp.RADARR
    if key == RefinerArrApp.SONARR.value:
        return RefinerArrApp.SONARR
    raise ValueError(f"unknown refiner arr app: {raw!r}")


def plan_failed_import_cleanup(
    app: RefinerArrApp,
    *,
    status_message_blob: str,
    policy: FailedImportCleanupPolicy,
    queue_item_id: int | None = None,
) -> FailedImportCleanupPlanningResult:
    """Route cleanup planning to the Radarr or Sonarr seam; no HTTP or deletes.

    ``queue_item_id`` is passed through as ``radarr_queue_item_id`` or
    ``sonarr_queue_item_id`` on the returned plan.
    """
    if app == RefinerArrApp.RADARR:
        return plan_radarr_failed_import_cleanup(
            status_message_blob=status_message_blob,
            policy=policy,
            radarr_queue_item_id=queue_item_id,
        )
    if app == RefinerArrApp.SONARR:
        return plan_sonarr_failed_import_cleanup(
            status_message_blob=status_message_blob,
            policy=policy,
            sonarr_queue_item_id=queue_item_id,
        )
    raise AssertionError(f"unhandled RefinerArrApp: {app!r}")
