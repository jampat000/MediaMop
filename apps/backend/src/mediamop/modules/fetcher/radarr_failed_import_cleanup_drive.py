"""Radarr-only live queue fetch + failed-import cleanup drive.

Fetches raw Radarr v3 queue rows through a narrow Protocol, builds a single
``status_message_blob`` string per row for the existing planner, and invokes
:func:`run_radarr_failed_import_cleanup_vertical` once per item. No Sonarr, no
shared *arr live driver.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Mapping, Protocol, Sequence

from mediamop.modules.fetcher.radarr_cleanup_execution import (
    RadarrFailedImportCleanupExecutionOutcome,
    RadarrQueueOperations,
)
from mediamop.modules.fetcher.radarr_failed_import_cleanup_vertical import (
    RadarrFailedImportCleanupSettingsSource,
    run_radarr_failed_import_cleanup_vertical,
)


class RadarrQueueFetchOperations(Protocol):
    """Narrow Radarr queue read surface (list rows as API-shaped mappings)."""

    def fetch_radarr_queue_items(self) -> Sequence[Mapping[str, Any]]:
        """Return queue item dicts (e.g. from ``GET /api/v3/queue``)."""
        ...


@dataclass(frozen=True, slots=True)
class RadarrFailedImportCleanupDriveItemResult:
    """One queue row after running the wired vertical."""

    radarr_queue_item_id: int | None
    status_message_blob: str
    outcome: RadarrFailedImportCleanupExecutionOutcome


def radarr_queue_item_status_message_blob(row: Mapping[str, Any]) -> str:
    """Flatten Radarr queue ``statusMessages`` and status-like fields into one string."""
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


def _radarr_queue_item_id(row: Mapping[str, Any]) -> int | None:
    for k in ("id", "Id"):
        v = row.get(k)
        if isinstance(v, bool):
            continue
        if isinstance(v, int):
            return v
        if isinstance(v, float) and v.is_integer():
            return int(v)
    return None


def drive_radarr_failed_import_cleanup_from_live_queue(
    settings: RadarrFailedImportCleanupSettingsSource,
    *,
    queue_fetch_client: RadarrQueueFetchOperations,
    queue_operations: RadarrQueueOperations,
) -> tuple[RadarrFailedImportCleanupDriveItemResult, ...]:
    """For each fetched queue row, run the existing Radarr cleanup vertical."""
    results: list[RadarrFailedImportCleanupDriveItemResult] = []
    for row in queue_fetch_client.fetch_radarr_queue_items():
        qid = _radarr_queue_item_id(row)
        blob = radarr_queue_item_status_message_blob(row)
        outcome = run_radarr_failed_import_cleanup_vertical(
            settings,
            status_message_blob=blob,
            radarr_queue_item_id=qid,
            queue_client=queue_operations,
        )
        results.append(
            RadarrFailedImportCleanupDriveItemResult(
                radarr_queue_item_id=qid,
                status_message_blob=blob,
                outcome=outcome,
            ),
        )
    return tuple(results)


class RadarrQueueHttpFetchClient:
    """Minimal stdlib HTTP client: ``GET {base}/api/v3/queue`` with ``X-Api-Key``."""

    def __init__(self, base_url: str, api_key: str, *, timeout_seconds: float = 30.0) -> None:
        self._base = base_url.rstrip("/")
        self._api_key = api_key
        self._timeout = timeout_seconds

    def fetch_radarr_queue_items(self) -> list[dict[str, Any]]:
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
            raise RuntimeError(f"Radarr queue fetch failed: HTTP {e.code} for {url!r}") from e
        data = json.loads(raw)
        if isinstance(data, list):
            return [x for x in data if isinstance(x, dict)]
        if isinstance(data, dict):
            rec = data.get("records")
            if isinstance(rec, list):
                return [x for x in rec if isinstance(x, dict)]
        return []
