"""Building blocks for the processing scenarios: a working server, a library, a manager, a hand-off.

Every step goes through the public API. The only things a scenario controls from outside are the
ones Weir itself does not own: the files on disk, the fake ffmpeg, and the fake media manager.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, TypeVar

from tests.contract.support import seed
from tests.contract.support.client import API, WeirClient
from tests.contract.support.fake_ffmpeg import FakeFfmpeg
from tests.contract.support.fake_manager import FakeManager
from tests.contract.support.launcher import ServerUnderTest
from tests.contract.support.polling import wait_until

T = TypeVar("T")

WEBHOOK_SECRET = "contract-webhook-secret-0123456789"
REMUX_KIND = "refiner.file.remux_pass.v1"
PASS_THROUGH_KIND = "refiner.file.pass_through.v1"
REJECT_KIND = "refiner.file.reject.v1"
DELUNO_LIBRARY_KEY = "5f2c0a9e"
DELUNO_OUTPUT_ROOT = "/deluno/processed/movies"
EVENTS_PATH = "/api/integrations/processors/events"


def working_env(fake_ffmpeg: FakeFfmpeg, **extra: str) -> dict[str, str]:
    """A server that actually works files: one worker, fake tools, and a webhook secret."""

    return {
        **fake_ffmpeg.env,
        "WEIR_REFINER_WORKER_COUNT": "1",
        "WEIR_MEDIA_MANAGER_WEBHOOK_SECRET": WEBHOOK_SECRET,
        **extra,
    }


@dataclass
class Folders:
    watched: Path
    work: Path
    output: Path

    @classmethod
    def make(cls, root: Path) -> Folders:
        folders = cls(root / "watched", root / "work", root / "output")
        for path in (folders.watched, folders.work, folders.output):
            path.mkdir(parents=True, exist_ok=True)
        return folders


def relax_operator_guards(admin: WeirClient) -> None:
    """No minimum age, size or free space, so a small fresh fixture file is processed at once."""

    r = admin.put_csrf(
        f"{API}/refiner/operator-settings",
        {"min_file_age_seconds": 0, "refiner_min_input_file_size_mb": 0, "minimum_free_disk_space_mb": 0},
    )
    assert r.status_code == 200, r.text


def create_library(admin: WeirClient, folders: Folders, **overrides: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "name": overrides.pop("name", "Contract Movies"),
        "media_type": "movie",
        "watched_folder": str(folders.watched),
        "work_folder": str(folders.work),
        "output_folder": str(folders.output),
        "min_file_age_seconds": 0,
        "file_detection_interval_seconds": 0,
        "skip_access_tests": True,
        "retry_backoff_seconds": 1,
        **overrides,
    }
    r = admin.post_csrf(f"{API}/refiner/libraries", body)
    assert r.status_code == 201, r.text
    return r.json()


def update_library(admin: WeirClient, library: dict[str, Any], **changes: Any) -> dict[str, Any]:
    r = admin.get(f"{API}/refiner/libraries/{library['id']}")
    assert r.status_code == 200, r.text
    current = r.json()
    r = admin.put_csrf(f"{API}/refiner/libraries/{library['id']}", _library_put_body(current, changes))
    assert r.status_code == 200, r.text
    return r.json()


def _library_put_body(current: dict[str, Any], changes: dict[str, Any]) -> dict[str, Any]:
    """The PUT body is the create body; take the writable fields from the current library."""

    writable = (
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
    )
    body = {key: current[key] for key in writable if key in current}
    body.update(changes)
    return body


def create_connection(admin: WeirClient, fake: FakeManager, **overrides: Any) -> dict[str, Any]:
    body = {
        "kind": fake.kind,
        "name": overrides.pop("name", f"Contract {fake.kind.capitalize()}"),
        "base_url": fake.base_url,
        "api_key": fake.api_key,
        **overrides,
    }
    r = admin.post_csrf(f"{API}/media-managers/connections", body)
    assert r.status_code in (200, 201), r.text
    return r.json()


def deluno_library_manifest(folders: Folders) -> dict[str, Any]:
    return {
        "id": DELUNO_LIBRARY_KEY,
        "name": "Movies",
        "mediaType": "movies",
        "rootPath": "/deluno/library/movies",
        "importWorkflow": "refine-before-import",
        "processorOutputPath": DELUNO_OUTPUT_ROOT,
    }


def post_handoff(
    client: WeirClient,
    *,
    handoff_id: str,
    source_path: Path,
    release_name: str = "Contract.Release.2024",
) -> dict[str, Any]:
    r = client.post(
        f"{API}/intake/webhook/deluno",
        json={
            "eventType": "deluno.processor-handoff",
            "handoffId": handoff_id,
            "libraryId": DELUNO_LIBRARY_KEY,
            "mediaType": "movies",
            "sourcePath": str(source_path),
            "releaseName": release_name,
            "callbackPath": EVENTS_PATH,
        },
        headers={"X-Webhook-Secret": WEBHOOK_SECRET},
    )
    assert r.status_code == 200, r.text
    return r.json()


def handoff_status(client: WeirClient, handoff_id: str) -> dict[str, Any]:
    r = client.get(f"{API}/intake/handoffs/deluno/{handoff_id}", headers={"X-Webhook-Secret": WEBHOOK_SECRET})
    assert r.status_code == 200, r.text
    return r.json()


def wait_for_handoff_state(client: WeirClient, handoff_id: str, state: str, *, timeout_s: float = 90.0) -> dict:
    def probe() -> dict[str, Any] | None:
        status = handoff_status(client, handoff_id)
        return status if status["state"] == state else None

    return wait_until(probe, timeout_s=timeout_s, what=f"hand-off {handoff_id} to reach {state!r}")


def jobs(admin: WeirClient, *, kind: str | None = None) -> list[dict[str, Any]]:
    r = admin.get(f"{API}/refiner/jobs/inspection", params={"limit": 100})
    assert r.status_code == 200, r.text
    rows = r.json()["jobs"]
    return [row for row in rows if kind is None or row["job_kind"] == kind]


def files(admin: WeirClient, *, library_id: int | None = None) -> list[dict[str, Any]]:
    params: dict[str, Any] = {"limit": 1000}
    if library_id is not None:
        params["library_id"] = library_id
    r = admin.get(f"{API}/refiner/files", params=params)
    assert r.status_code == 200, r.text
    return r.json()["files"]


def file_row(admin: WeirClient, library_id: int, relative_path: str) -> dict[str, Any] | None:
    for row in files(admin, library_id=library_id):
        if row["relative_path"] == relative_path:
            return row
    return None


def wait_for_file_status(
    admin: WeirClient, library_id: int, relative_path: str, status: str, *, timeout_s: float = 90.0
) -> dict[str, Any]:
    def probe() -> dict[str, Any] | None:
        row = file_row(admin, library_id, relative_path)
        return row if row is not None and row["status"] == status else None

    return wait_until(probe, timeout_s=timeout_s, what=f"{relative_path} to reach status {status!r}")


def enqueue_scan(admin: WeirClient, library: dict[str, Any], *, enqueue_remux_jobs: bool = True) -> int:
    r = admin.post_csrf(
        f"{API}/refiner/jobs/watched-folder-remux-scan-dispatch/enqueue",
        {"media_scope": library["media_type"], "library_id": library["id"], "enqueue_remux_jobs": enqueue_remux_jobs},
    )
    assert r.status_code == 200, r.text
    return int(r.json()["job_id"])


def detect_without_queueing(admin: WeirClient, library: dict[str, Any], relative_path: str) -> dict[str, Any]:
    """Let a scan notice the file (recording its size) without queueing it, as a periodic scan would have.

    Needed before a hand-off whose retries a scenario counts: a file Weir has only ever seen through a
    hand-off has no recorded size, so the first scan after a failure treats it as a changed source and
    starts its failure count again (#531 item 1; the correct behaviour — a hand-off's fingerprint is
    recorded up front, so a scan never resets it — is asserted in
    ``tests/contract/processing/test_handoff_retry_correctness.py``).
    """

    enqueue_scan(admin, library, enqueue_remux_jobs=False)

    def probe() -> dict[str, Any] | None:
        row = file_row(admin, library["id"], relative_path)
        return row if row is not None and int(row["size_bytes"] or 0) > 0 else None

    return wait_until(probe, timeout_s=60, what=f"a scan to record {relative_path}")


def activity(admin: WeirClient, event_type: str) -> list[dict[str, Any]]:
    r = admin.get(f"{API}/activity/recent", params={"event_type": event_type, "limit": 100})
    assert r.status_code == 200, r.text
    return r.json()["items"]


def drive_retries_until(
    admin: WeirClient,
    library: dict[str, Any],
    probe: Callable[[], T | None],
    *,
    what: str,
    timeout_s: float = 120.0,
) -> T:
    """Let automatic retries happen, as the periodic watched-folder scan would, until ``probe`` is truthy.

    A failed file is picked up again by a scan once its backoff has passed. Rather than wait out the
    scan timer, the scenario asks for a scan while a file waits for its retry and no scan is queued.
    """

    last_scan = [0.0]

    def step() -> T | None:
        found = probe()
        if found:
            return found
        now = time.monotonic()
        waiting = any(row["status"] == "processing_failed" for row in files(admin, library_id=library["id"]))
        if waiting and now - last_scan[0] >= 2.0 and not _scan_pending(admin):
            enqueue_scan(admin, library)
            last_scan[0] = now
        return None

    return wait_until(step, timeout_s=timeout_s, interval_s=0.5, what=what)


def failure_attempts_reach(
    admin: WeirClient, library: dict[str, Any], relative_path: str, attempts: int, *, timeout_s: float = 120.0
) -> dict[str, Any]:
    """Drive retries until the file has failed ``attempts`` times and is not being worked on."""

    def probe() -> dict[str, Any] | None:
        row = file_row(admin, library["id"], relative_path)
        if row is not None and int(row.get("failure_attempts") or 0) >= attempts and row["status"] != "processing":
            return row
        return None

    return drive_retries_until(
        admin, library, probe, what=f"{relative_path} to fail {attempts} times", timeout_s=timeout_s
    )


def _scan_pending(admin: WeirClient) -> bool:
    return any(
        job["status"] in ("pending", "leased") and job["job_kind"].startswith("refiner.watched_folder")
        for job in jobs(admin)
    )


def file_state_after_stop(server: ServerUnderTest, library_id: int, relative_path: str) -> dict[str, Any]:
    """The ``refiner_files`` row, read from SQLite with the server stopped (and started again).

    Used where ``GET /refiner/files`` cannot answer: it fails with HTTP 500 for any page that contains a
    ``passed_through`` or ``rejected`` row, because its response schema does not list those statuses
    (#530; the correct behaviour is asserted in
    ``tests/contract/refiner/test_refiner_files_pass_through_reject_status.py``).
    """

    with seed.stopped(server) as conn:
        found = seed.rows(
            conn,
            "SELECT * FROM refiner_files WHERE library_id = ? AND relative_path = ?",
            (library_id, relative_path),
        )
    assert len(found) == 1, found
    return found[0]


def callbacks(fake: FakeManager, handoff_id: str) -> list[dict[str, Any]]:
    return [r.json for r in fake.requests_to("POST", EVENTS_PATH) if (r.json or {}).get("handoffId") == handoff_id]


def never_within(check: Callable[[], bool], *, seconds: float, what: str) -> None:
    """Assert ``check`` stays false for ``seconds`` (polling), for "this must not happen" claims."""

    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        assert not check(), f"{what} happened, but it must not"
        time.sleep(0.25)


def deluno_setup(
    admin: WeirClient,
    fake_managers: Callable[..., FakeManager],
    folders: Folders,
    *,
    capabilities: list[str] | None = None,
    **library: Any,
) -> tuple[FakeManager, dict[str, Any]]:
    """A fake Deluno that manages this library, its connection, relaxed guards, and the linked library."""

    fake = fake_managers("deluno", capabilities=capabilities or [])
    fake.libraries.append(deluno_library_manifest(folders))
    connection = create_connection(admin, fake)
    relax_operator_guards(admin)
    created = create_library(admin, folders, manager_connection_ids=[connection["id"]], **library)
    return fake, created


def set_pause(admin: WeirClient, *, paused: bool) -> dict[str, Any]:
    r = admin.put_csrf(f"{API}/pause", {"paused": paused, "scan_while_paused": True})
    assert r.status_code == 200, r.text
    assert r.json()["paused"] is paused
    return r.json()


def start_working_server(
    server_factory: Callable[..., ServerUnderTest], fake_ffmpeg: FakeFfmpeg, **extra_env: str
) -> ServerUnderTest:
    return server_factory(env=working_env(fake_ffmpeg, **extra_env))
