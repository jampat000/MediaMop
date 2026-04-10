"""Sonarr-only live queue fetch + failed-import cleanup drive (Pass 12.5).

Fetches raw Sonarr v3 queue rows through a narrow Protocol, builds a single
``status_message_blob`` string per row for the existing planner, and invokes
:func:`run_sonarr_failed_import_cleanup_vertical` once per item. No Radarr, no
shared *arr live driver.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Mapping, Protocol, Sequence

from mediamop.modules.refiner.sonarr_cleanup_execution import (
    SonarrFailedImportCleanupExecutionOutcome,
    SonarrQueueOperations,
)
from mediamop.modules.refiner.sonarr_failed_import_cleanup_vertical import (
    SonarrFailedImportCleanupSettingsSource,
    run_sonarr_failed_import_cleanup_vertical,
)


class SonarrQueueFetchOperations(Protocol):
    """Narrow Sonarr queue read surface (list rows as API-shaped mappings)."""

    def fetch_sonarr_queue_items(self) -> Sequence[Mapping[str, Any]]:
        """Return queue item dicts (e.g. from ``GET /api/v3/queue``)."""
        ...


@dataclass(frozen=True, slots=True)
class SonarrFailedImportCleanupDriveItemResult:
    """One queue row after running the wired vertical."""

    sonarr_queue_item_id: int | None
    status_message_blob: str
    outcome: SonarrFailedImportCleanupExecutionOutcome


def sonarr_queue_item_status_message_blob(row: Mapping[str, Any]) -> str:
    """Flatten Sonarr queue ``statusMessages`` and status-like fields into one string."""
    parts: list[str] = []
    sm = row.get("statusMessages") or row.get("status_messages")
    if isinstance(sm, list):
        for entry in sm:
            if not isinstance(entry, dict):
                continue
            for mk in ("messages", "Messages"):
                msgs = entry.get(mk)
                if isinstance(msgs, list):
                    for m in msgs:
                        if isinstance(m, str) and m.strip():
                            parts.append(m.strip())
            title = entry.get("title") or entry.get("Title")
            if isinstance(title, str) and title.strip():
                parts.append(title.strip())
    for k in ("status", "trackedDownloadStatus", "trackedDownloadState"):
        v = row.get(k)
        if isinstance(v, str) and v.strip():
            parts.append(v.strip())
    return " ".join(parts).strip()


def _sonarr_queue_item_id(row: Mapping[str, Any]) -> int | None:
    for k in ("id", "Id"):
        v = row.get(k)
        if isinstance(v, bool):
            continue
        if isinstance(v, int):
            return v
        if isinstance(v, float) and v.is_integer():
            return int(v)
    return None


def drive_sonarr_failed_import_cleanup_from_live_queue(
    settings: SonarrFailedImportCleanupSettingsSource,
    *,
    queue_fetch_client: SonarrQueueFetchOperations,
    queue_operations: SonarrQueueOperations,
) -> tuple[SonarrFailedImportCleanupDriveItemResult, ...]:
    """For each fetched queue row, run the existing Sonarr cleanup vertical."""
    results: list[SonarrFailedImportCleanupDriveItemResult] = []
    for row in queue_fetch_client.fetch_sonarr_queue_items():
        qid = _sonarr_queue_item_id(row)
        blob = sonarr_queue_item_status_message_blob(row)
        outcome = run_sonarr_failed_import_cleanup_vertical(
            settings,
            status_message_blob=blob,
            sonarr_queue_item_id=qid,
            queue_client=queue_operations,
        )
        results.append(
            SonarrFailedImportCleanupDriveItemResult(
                sonarr_queue_item_id=qid,
                status_message_blob=blob,
                outcome=outcome,
            ),
        )
    return tuple(results)


class SonarrQueueHttpFetchClient:
    """Minimal stdlib HTTP client: ``GET {base}/api/v3/queue`` with ``X-Api-Key``."""

    def __init__(self, base_url: str, api_key: str, *, timeout_seconds: float = 30.0) -> None:
        self._base = base_url.rstrip("/")
        self._api_key = api_key
        self._timeout = timeout_seconds

    def fetch_sonarr_queue_items(self) -> list[dict[str, Any]]:
        url = f"{self._base}/api/v3/queue?pageSize=1000"
        req = urllib.request.Request(
            url,
            method="GET",
            headers={"X-Api-Key": self._api_key, "Accept": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=self._timeout) as resp:
                raw = resp.read().decode("utf-8")
        except urllib.error.HTTPError as e:
            raise RuntimeError(f"Sonarr queue fetch failed: HTTP {e.code} for {url!r}") from e
        data = json.loads(raw)
        if isinstance(data, list):
            return [x for x in data if isinstance(x, dict)]
        if isinstance(data, dict):
            rec = data.get("records")
            if isinstance(rec, list):
                return [x for x in rec if isinstance(x, dict)]
        return []
