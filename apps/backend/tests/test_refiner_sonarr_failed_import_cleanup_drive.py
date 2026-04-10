"""Refiner Pass 12.5: Sonarr live queue fetch + cleanup drive (Sonarr-only)."""

from __future__ import annotations

from dataclasses import dataclass, replace
from unittest.mock import patch

from mediamop.core.config import MediaMopSettings
from mediamop.modules.refiner.failed_import_cleanup_settings import (
    AppFailedImportCleanupPolicySettings,
    RefinerFailedImportCleanupSettingsBundle,
)
from mediamop.modules.refiner.sonarr_cleanup_execution import SonarrFailedImportCleanupExecutionOutcome
from mediamop.modules.refiner.sonarr_failed_import_cleanup_drive import (
    drive_sonarr_failed_import_cleanup_from_live_queue,
    sonarr_queue_item_status_message_blob,
)
from mediamop.modules.refiner.sonarr_failed_import_cleanup_vertical import (
    run_sonarr_failed_import_cleanup_vertical,
)


@dataclass
class _FakeFetch:
    rows: list[dict]

    def fetch_sonarr_queue_items(self):
        return self.rows


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


def _row_import_failed(*, qid: int) -> dict:
    return {
        "id": qid,
        "status": "importPending",
        "statusMessages": [{"title": "Import", "messages": ["Import failed: path missing"]}],
    }


def _row_waiting(*, qid: int) -> dict:
    return {
        "id": qid,
        "status": "importPending",
        "statusMessages": [
            {"title": "Import", "messages": ["Downloaded - Waiting to Import"]},
        ],
    }


def test_drive_terminal_message_and_enabled_toggle_removes_queue_item() -> None:
    settings = _settings_with_sonarr_policy(
        AppFailedImportCleanupPolicySettings(remove_failed_imports=True),
    )
    client = _RecordingSonarrClient()
    fetch = _FakeFetch([_row_import_failed(qid=88)])
    results = drive_sonarr_failed_import_cleanup_from_live_queue(
        settings,
        queue_fetch_client=fetch,
        queue_operations=client,
    )
    assert len(results) == 1
    assert results[0].outcome is SonarrFailedImportCleanupExecutionOutcome.REMOVED_QUEUE_ITEM
    assert results[0].sonarr_queue_item_id == 88
    assert "Import failed" in results[0].status_message_blob
    assert client.calls == [88]


def test_drive_waiting_only_message_no_op_no_client_call() -> None:
    settings = _settings_with_sonarr_policy(AppFailedImportCleanupPolicySettings())
    client = _RecordingSonarrClient()
    fetch = _FakeFetch([_row_waiting(qid=4)])
    results = drive_sonarr_failed_import_cleanup_from_live_queue(
        settings,
        queue_fetch_client=fetch,
        queue_operations=client,
    )
    assert results[0].outcome is SonarrFailedImportCleanupExecutionOutcome.NO_OP
    assert client.calls == []


def test_drive_missing_queue_id_uses_vertical_skip_path() -> None:
    settings = _settings_with_sonarr_policy(
        AppFailedImportCleanupPolicySettings(remove_quality_rejections=True),
    )
    client = _RecordingSonarrClient()
    row = {
        "statusMessages": [{"messages": ["Not an upgrade for existing movie file"]}],
    }
    fetch = _FakeFetch([row])
    results = drive_sonarr_failed_import_cleanup_from_live_queue(
        settings,
        queue_fetch_client=fetch,
        queue_operations=client,
    )
    assert results[0].sonarr_queue_item_id is None
    assert results[0].outcome is SonarrFailedImportCleanupExecutionOutcome.SKIPPED_MISSING_QUEUE_ITEM_ID
    assert client.calls == []


def test_drive_delegates_to_vertical_not_parallel_planner() -> None:
    settings = _settings_with_sonarr_policy(AppFailedImportCleanupPolicySettings())
    client = _RecordingSonarrClient()
    fetch = _FakeFetch([_row_import_failed(qid=2)])
    with patch(
        "mediamop.modules.refiner.sonarr_failed_import_cleanup_drive.run_sonarr_failed_import_cleanup_vertical",
        wraps=run_sonarr_failed_import_cleanup_vertical,
    ) as spy:
        drive_sonarr_failed_import_cleanup_from_live_queue(
            settings,
            queue_fetch_client=fetch,
            queue_operations=client,
        )
    assert spy.call_count == 1
    _, kwargs = spy.call_args
    assert kwargs["queue_client"] is client
    assert kwargs["sonarr_queue_item_id"] == 2


def test_drive_empty_queue_no_vertical_calls() -> None:
    settings = _settings_with_sonarr_policy(AppFailedImportCleanupPolicySettings())
    client = _RecordingSonarrClient()
    fetch = _FakeFetch([])
    with patch(
        "mediamop.modules.refiner.sonarr_failed_import_cleanup_drive.run_sonarr_failed_import_cleanup_vertical",
    ) as spy:
        results = drive_sonarr_failed_import_cleanup_from_live_queue(
            settings,
            queue_fetch_client=fetch,
            queue_operations=client,
        )
    spy.assert_not_called()
    assert results == ()


def test_status_blob_joins_status_messages_and_status_fields() -> None:
    row = {
        "status": "importPending",
        "trackedDownloadStatus": "completed",
        "statusMessages": [{"title": "T", "messages": ["m1", "m2"]}],
    }
    blob = sonarr_queue_item_status_message_blob(row)
    assert "m1" in blob and "m2" in blob and "T" in blob
    assert "importPending" in blob or "importpending" in blob.lower()
    assert "completed" in blob.lower()
