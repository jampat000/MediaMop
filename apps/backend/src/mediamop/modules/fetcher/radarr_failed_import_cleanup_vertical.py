"""Radarr-only wired vertical: settings → plan → execute.

Uses :meth:`radarr_failed_import_cleanup_policy` on the injected settings source so
``MediaMopSettings`` works without importing it here (avoids config↔refiner cycles).
Parallel Sonarr entry: :mod:`mediamop.modules.fetcher.sonarr_failed_import_cleanup_vertical`.
"""

from __future__ import annotations

from typing import Protocol

from mediamop.modules.arr_failed_import.policy import FailedImportCleanupPolicy
from mediamop.modules.fetcher.radarr_cleanup_execution import (
    RadarrFailedImportCleanupExecutionOutcome,
    RadarrQueueOperations,
    execute_radarr_failed_import_cleanup_plan,
)
from mediamop.modules.fetcher.radarr_failed_import_cleanup import plan_radarr_failed_import_cleanup


class RadarrFailedImportCleanupSettingsSource(Protocol):
    """Anything that supplies the resolved Radarr cleanup policy (e.g. ``MediaMopSettings``)."""

    def radarr_failed_import_cleanup_policy(self) -> FailedImportCleanupPolicy:
        ...


def run_radarr_failed_import_cleanup_vertical(
    settings: RadarrFailedImportCleanupSettingsSource,
    *,
    status_message_blob: str,
    radarr_queue_item_id: int | None,
    queue_client: RadarrQueueOperations,
) -> RadarrFailedImportCleanupExecutionOutcome:
    """Resolve Radarr policy from ``settings``, plan, then execute — no reclassification.

    Delegates to :func:`plan_radarr_failed_import_cleanup` and
    :func:`execute_radarr_failed_import_cleanup_plan` only.
    """
    policy = settings.radarr_failed_import_cleanup_policy()
    plan = plan_radarr_failed_import_cleanup(
        status_message_blob=status_message_blob,
        policy=policy,
        radarr_queue_item_id=radarr_queue_item_id,
    )
    return execute_radarr_failed_import_cleanup_plan(plan, queue_client)
