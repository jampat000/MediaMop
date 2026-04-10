"""Refiner Pass 11.5: Sonarr wired vertical — settings → plan → execute (Sonarr-only)."""

from __future__ import annotations

from dataclasses import dataclass, replace

from mediamop.core.config import MediaMopSettings
from mediamop.modules.refiner.failed_import_cleanup_settings import (
    AppFailedImportCleanupPolicySettings,
    RefinerFailedImportCleanupSettingsBundle,
)
from mediamop.modules.refiner.sonarr_cleanup_execution import SonarrFailedImportCleanupExecutionOutcome
from mediamop.modules.refiner.sonarr_failed_import_cleanup_vertical import (
    run_sonarr_failed_import_cleanup_vertical,
)


@dataclass
class _RecordingSonarrClient:
    calls: list[int]

    def __init__(self) -> None:
        self.calls = []

    def remove_queue_item(self, queue_item_id: int) -> None:
        self.calls.append(queue_item_id)


def _settings_with_sonarr_policy(sonarr: AppFailedImportCleanupPolicySettings) -> MediaMopSettings:
    base = MediaMopSettings.load()
    bundle = RefinerFailedImportCleanupSettingsBundle(
        radarr=base.refiner_failed_import_cleanup.radarr,
        sonarr=sonarr,
    )
    return replace(base, refiner_failed_import_cleanup=bundle)


def test_sonarr_vertical_resolves_policy_plans_and_executes_when_eligible() -> None:
    sonarr = AppFailedImportCleanupPolicySettings(remove_failed_imports=True)
    settings = _settings_with_sonarr_policy(sonarr)
    client = _RecordingSonarrClient()
    out = run_sonarr_failed_import_cleanup_vertical(
        settings,
        status_message_blob="Import failed",
        sonarr_queue_item_id=602,
        queue_client=client,
    )
    assert out is SonarrFailedImportCleanupExecutionOutcome.REMOVED_QUEUE_ITEM
    assert client.calls == [602]


def test_sonarr_vertical_no_op_path_no_client_call() -> None:
    settings = _settings_with_sonarr_policy(AppFailedImportCleanupPolicySettings())
    client = _RecordingSonarrClient()
    out = run_sonarr_failed_import_cleanup_vertical(
        settings,
        status_message_blob="Downloaded - Waiting to Import",
        sonarr_queue_item_id=9,
        queue_client=client,
    )
    assert out is SonarrFailedImportCleanupExecutionOutcome.NO_OP
    assert client.calls == []


def test_sonarr_vertical_planned_remove_without_queue_id_skips_client() -> None:
    sonarr = AppFailedImportCleanupPolicySettings(remove_corrupt_imports=True)
    settings = _settings_with_sonarr_policy(sonarr)
    client = _RecordingSonarrClient()
    out = run_sonarr_failed_import_cleanup_vertical(
        settings,
        status_message_blob="file is corrupt",
        sonarr_queue_item_id=None,
        queue_client=client,
    )
    assert out is SonarrFailedImportCleanupExecutionOutcome.SKIPPED_MISSING_QUEUE_ITEM_ID
    assert client.calls == []
