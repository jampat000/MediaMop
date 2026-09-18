"""Shared helpers for the jobs contract tests: job rows, library folders, and the inspection API."""

from __future__ import annotations

import sqlite3
from datetime import datetime
from typing import Any

from tests.contract.support import seed
from tests.contract.support.client import API, WeirClient

VIEWER_USERNAME = "bob"
VIEWER_PASSWORD = "viewer-password-here"

ALL_STATUSES = ("pending", "leased", "completed", "failed", "handler_ok_finalize_failed", "cancelled")

# ``ProcessingLibraryOut`` fields that ``PUT /processing/libraries/{id}`` does not accept (it forbids extras).
_LIBRARY_READ_ONLY = frozenset(
    {
        "id",
        "display_order",
        "manager_coverage",
        "manager_coverage_detail",
        "discovered_from_connection_id",
        "discovered_library_key",
        "active_job_count",
        "updated_at",
    }
)


def insert_job(
    conn: sqlite3.Connection,
    *,
    dedupe_key: str,
    job_kind: str,
    status: str = "pending",
    updated_at: datetime | None = None,
    **columns: Any,
) -> int:
    """One ``jobs`` row. Extra columns (``attempt_count``, ``last_error``, ...) pass through."""

    stamp = seed.utc_text(updated_at)
    values: dict[str, Any] = {
        "dedupe_key": dedupe_key,
        "job_kind": job_kind,
        "status": status,
        "created_at": stamp,
        "updated_at": stamp,
        **columns,
    }
    names = ", ".join(values)
    marks = ", ".join("?" for _ in values)
    cur = conn.execute(f"INSERT INTO jobs ({names}) VALUES ({marks})", tuple(values.values()))
    return int(cur.lastrowid or 0)


def ensure_viewer(conn: sqlite3.Connection) -> None:
    if seed.scalar(conn, "SELECT COUNT(*) FROM users WHERE username = ?", (VIEWER_USERNAME,)) == 0:
        seed.insert_user(conn, username=VIEWER_USERNAME, password=VIEWER_PASSWORD, role="viewer")


def inspection(client: WeirClient, *, statuses: tuple[str, ...] = (), limit: int = 100) -> dict[str, Any]:
    params: list[tuple[str, str | int]] = [("limit", limit), *(("status", s) for s in statuses)]
    r = client.get(f"{API}/processing/jobs/inspection", params=params)
    assert r.status_code == 200, r.text
    return r.json()


def all_jobs(client: WeirClient) -> list[dict[str, Any]]:
    return list(inspection(client, statuses=ALL_STATUSES)["jobs"])


def job_by_id(client: WeirClient, job_id: int) -> dict[str, Any]:
    found = [job for job in all_jobs(client) if job["id"] == job_id]
    assert found, f"job {job_id} is not in the inspection list"
    return found[0]


def library_for_scope(client: WeirClient, media_type: str = "movie") -> dict[str, Any]:
    """The library scope-only work resolves to: first of that media type in display order."""

    r = client.get(f"{API}/processing/libraries")
    assert r.status_code == 200, r.text
    libraries = sorted(
        (lib for lib in r.json() if lib["media_type"] == media_type), key=lambda lib: (lib["display_order"], lib["id"])
    )
    assert libraries, f"no {media_type} library"
    return libraries[0]


def save_library(client: WeirClient, library_id: int, **changes: Any) -> dict[str, Any]:
    """Save one library whole, from its current values plus ``changes``."""

    r = client.get(f"{API}/processing/libraries/{library_id}")
    assert r.status_code == 200, r.text
    body = {key: value for key, value in r.json().items() if key not in _LIBRARY_READ_ONLY}
    body.update(changes)
    saved = client.put_csrf(f"{API}/processing/libraries/{library_id}", json=body)
    assert saved.status_code == 200, saved.text
    return saved.json()


def set_movie_folders(client: WeirClient, *, watched: str | None, output: str, work: str | None = None) -> int:
    library = library_for_scope(client, "movie")
    save_library(client, library["id"], watched_folder=watched or "", work_folder=work or "", output_folder=output)
    return int(library["id"])
