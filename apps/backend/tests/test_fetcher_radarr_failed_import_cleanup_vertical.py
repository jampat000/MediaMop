"""Radarr wired vertical — settings → plan → execute (Radarr-only)."""

from __future__ import annotations

from dataclasses import dataclass, replace

from mediamop.core.config import MediaMopSettings
from mediamop.modules.arr_failed_import.env_settings import (
    AppFailedImportCleanupPolicySettings,
    FailedImportCleanupSettingsBundle,
)
from mediamop.modules.fetcher.radarr_cleanup_execution import RadarrFailedImportCleanupExecutionOutcome
from mediamop.modules.fetcher.radarr_failed_import_cleanup_vertical import (
    run_radarr_failed_import_cleanup_vertical,
)


@dataclass
class _RecordingRadarrClient:
    calls: list[int]

    def __init__(self) -> None:
        self.calls = []

    def remove_queue_item(self, queue_item_id: int) -> None:
        self.calls.append(queue_item_id)


def _settings_with_radarr_policy(radarr: AppFailedImportCleanupPolicySettings) -> MediaMopSettings:
    base = MediaMopSettings.load()
    bundle = FailedImportCleanupSettingsBundle(
        radarr=radarr,
        sonarr=base.failed_import_cleanup_env.sonarr,
    )
    return replace(base, failed_import_cleanup_env=bundle)


def test_vertical_resolves_policy_plans_and_executes_when_eligible() -> None:
    radarr = AppFailedImportCleanupPolicySettings(
        remove_failed_imports=True,
    )
    settings = _settings_with_radarr_policy(radarr)
    client = _RecordingRadarrClient()
    out = run_radarr_failed_import_cleanup_vertical(
        settings,
        status_message_blob="Import failed",
        radarr_queue_item_id=501,
        queue_client=client,
    )
    assert out is RadarrFailedImportCleanupExecutionOutcome.REMOVED_QUEUE_ITEM
    assert client.calls == [501]


def test_vertical_no_op_path_no_client_call() -> None:
    settings = _settings_with_radarr_policy(AppFailedImportCleanupPolicySettings())
    client = _RecordingRadarrClient()
    out = run_radarr_failed_import_cleanup_vertical(
        settings,
        status_message_blob="Downloaded - Waiting to Import",
        radarr_queue_item_id=9,
        queue_client=client,
    )
    assert out is RadarrFailedImportCleanupExecutionOutcome.NO_OP
    assert client.calls == []


def test_vertical_planned_remove_without_queue_id_skips_client() -> None:
    radarr = AppFailedImportCleanupPolicySettings(
        remove_quality_rejections=True,
    )
    settings = _settings_with_radarr_policy(radarr)
    client = _RecordingRadarrClient()
    out = run_radarr_failed_import_cleanup_vertical(
        settings,
        status_message_blob="Not an upgrade for existing movie file",
        radarr_queue_item_id=None,
        queue_client=client,
    )
    assert out is RadarrFailedImportCleanupExecutionOutcome.SKIPPED_MISSING_QUEUE_ITEM_ID
    assert client.calls == []
