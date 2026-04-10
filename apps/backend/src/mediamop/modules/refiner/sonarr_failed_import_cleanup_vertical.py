"""Sonarr-only wired vertical: settings → plan → execute (Pass 11.5).

Uses :meth:`sonarr_failed_import_cleanup_policy` on the injected settings source so
``MediaMopSettings`` works without importing it here (avoids config↔refiner cycles).
Parallel Radarr entry: :mod:`mediamop.modules.refiner.radarr_failed_import_cleanup_vertical`.
"""

from __future__ import annotations

from typing import Protocol

from mediamop.modules.refiner.failed_import_cleanup_policy import FailedImportCleanupPolicy
from mediamop.modules.refiner.sonarr_cleanup_execution import (
    SonarrFailedImportCleanupExecutionOutcome,
    SonarrQueueOperations,
    execute_sonarr_failed_import_cleanup_plan,
)
from mediamop.modules.refiner.sonarr_failed_import_cleanup import plan_sonarr_failed_import_cleanup


class SonarrFailedImportCleanupSettingsSource(Protocol):
    """Anything that supplies the resolved Sonarr cleanup policy (e.g. ``MediaMopSettings``)."""

    def sonarr_failed_import_cleanup_policy(self) -> FailedImportCleanupPolicy:
        ...


def run_sonarr_failed_import_cleanup_vertical(
    settings: SonarrFailedImportCleanupSettingsSource,
    *,
    status_message_blob: str,
    sonarr_queue_item_id: int | None,
    queue_client: SonarrQueueOperations,
) -> SonarrFailedImportCleanupExecutionOutcome:
    """Resolve Sonarr policy from ``settings``, plan, then execute — no reclassification.

    Delegates to :func:`plan_sonarr_failed_import_cleanup` and
    :func:`execute_sonarr_failed_import_cleanup_plan` only.
    """
    policy = settings.sonarr_failed_import_cleanup_policy()
    plan = plan_sonarr_failed_import_cleanup(
        status_message_blob=status_message_blob,
        policy=policy,
        sonarr_queue_item_id=sonarr_queue_item_id,
    )
    return execute_sonarr_failed_import_cleanup_plan(plan, queue_client)
