"""Shared steps for the media manager contract tests: connections, libraries, hand-offs, job rows.

Everything goes through the public API, except where a test needs a state the API has no way to
create; those write SQL while the server is stopped (``tests/contract/support/seed.py``).
"""

from __future__ import annotations

import json
import socket
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

from tests.contract.support.client import API, WeirClient

REMUX_KIND = "processing.file.remux_pass.v1"
CALLBACK_PATH = "/api/integrations/processors/events"

#: No instance-wide webhook secret, whatever the developer's shell holds.
NO_WEBHOOK_SECRET = {"WEIR_MEDIA_MANAGER_WEBHOOK_SECRET": ""}


# --- media manager connections ------------------------------------------------------------------


def create_connection(client: WeirClient, **overrides: Any) -> httpx.Response:
    body: dict[str, Any] = {
        "kind": "deluno",
        "name": "Deluno",
        "base_url": "http://192.0.2.10:5099",
        "api_key": "deluno_secret_key",
    }
    body.update(overrides)
    return client.post_csrf(f"{API}/media-managers/connections", body)


def delete_connection(client: WeirClient, connection_id: int) -> httpx.Response:
    # The connection DELETE takes its CSRF token in a JSON body, like the web app sends it.
    return client.request(
        "DELETE",
        f"{API}/media-managers/connections/{connection_id}",
        json={"csrf_token": client.csrf()},
    )


def clear_connections(client: WeirClient) -> None:
    listed = client.get(f"{API}/media-managers/connections")
    assert listed.status_code == 200, listed.text
    for row in listed.json():
        assert delete_connection(client, row["id"]).status_code == 204


def closed_port_url() -> str:
    """An http address on this machine where nothing is listening."""

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    return f"http://127.0.0.1:{port}"


# --- Processing libraries --------------------------------------------------------------------------


@dataclass(frozen=True)
class LibraryFolders:
    watched: Path
    output: Path

    @classmethod
    def make(cls, root: Path) -> LibraryFolders:
        folders = cls(root / "watched", root / "output")
        folders.watched.mkdir(parents=True, exist_ok=True)
        folders.output.mkdir(parents=True, exist_ok=True)
        return folders


def create_library(
    client: WeirClient, *, name: str, media_type: str, folders: LibraryFolders, **overrides: Any
) -> dict[str, Any]:
    body: dict[str, Any] = {
        "name": name,
        "media_type": media_type,
        "watched_folder": str(folders.watched),
        "output_folder": str(folders.output),
        **overrides,
    }
    r = client.post_csrf(f"{API}/processing/libraries", body)
    assert r.status_code == 201, r.text
    return r.json()


_WRITABLE_LIBRARY_FIELDS = [
    "name",
    "media_type",
    "enabled",
    "watched_folder",
    "work_folder",
    "output_folder",
    "media_extensions_csv",
    "exclude_markers_csv",
    "include_patterns_csv",
    "exclude_patterns_csv",
    "min_file_size_mb",
    "max_file_size_mb",
    "rejected_file_action",
    "min_file_age_seconds",
    "exclude_hidden",
    "top_level_only",
    "sidecar_patterns_csv",
    "preserve_original_timestamps",
    "output_collision_policy",
    "hardware_decode_mode",
    "hardware_device",
    "hardware_disabled_vendors_csv",
    "ffmpeg_strictness",
    "scan_interval_seconds",
    "hold_minutes",
    "file_detection_interval_seconds",
    "ignore_size_changes",
    "skip_access_tests",
    "max_attempts",
    "retry_backoff_seconds",
    "retry_execution_failures",
    "failure_policy",
    "retry_preflight_failures",
    "schedule_grid",
    "file_system_events_enabled",
    "schedule_enabled",
    "schedule_hours_limited",
    "schedule_days",
    "schedule_start",
    "schedule_end",
    "max_concurrent_files",
    "priority",
    "rule_set_id",
    "manager_connection_ids",
    "remove_original_after_success",
]


def update_library(client: WeirClient, library: dict[str, Any], **changes: Any) -> dict[str, Any]:
    """PUT is a whole-library save, so start from the library as it is and change only ``changes``."""

    body = {key: library[key] for key in _WRITABLE_LIBRARY_FIELDS if key in library}
    body.update(changes)
    r = client.put_csrf(f"{API}/processing/libraries/{library['id']}", body)
    assert r.status_code == 200, r.text
    return r.json()


def ensure_library(
    client: WeirClient, *, name: str, media_type: str, folders: LibraryFolders, **overrides: Any
) -> dict[str, Any]:
    """The library named ``name`` with these folders: a fresh install's seeded one is pointed at them."""

    wanted = {"watched_folder": str(folders.watched), "output_folder": str(folders.output), **overrides}
    listed = client.get(f"{API}/processing/libraries")
    assert listed.status_code == 200, listed.text
    for row in listed.json():
        if row["name"] == name:
            if all(row.get(key) == value for key, value in wanted.items()):
                return row
            return update_library(client, row, media_type=media_type, **wanted)
    return create_library(client, name=name, media_type=media_type, folders=folders, **overrides)


# --- Processing job rows ---------------------------------------------------------------------------


def remux_jobs(client: WeirClient) -> list[dict[str, Any]]:
    """Every persisted remux job row (workers are off, so intake's rows stay where they were put)."""

    r = client.get(f"{API}/processing/jobs/inspection", params={"limit": 100})
    assert r.status_code == 200, r.text
    return [job for job in r.json()["jobs"] if job["job_kind"] == REMUX_KIND]


def payload(job: dict[str, Any]) -> dict[str, Any]:
    return json.loads(job["payload_json"] or "{}")


def handoff_dedupe_key(handoff_id: str, source_key: str = "deluno") -> str:
    return f"{REMUX_KIND}:{source_key}:handoff:{handoff_id}"
