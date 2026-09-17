"""Shared helpers for the Refiner contract tests."""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

import httpx

from tests.contract.support import seed
from tests.contract.support.client import WeirClient
from tests.contract.support.launcher import ServerUnderTest

VIEWER_USERNAME = "bob"
VIEWER_PASSWORD = "viewer-password-here"

REMUX_PASS_JOB_KIND = "refiner.file.remux_pass.v1"
REMUX_PASS_COMPLETED_EVENT = "refiner.file_remux_pass_completed"


def signed_in_admin(server: ServerUnderTest, client_factory: Callable[..., WeirClient]) -> WeirClient:
    """A new cookie jar on ``server``, signed in as the admin (bootstrapped when needed)."""

    c = client_factory(server)
    c.ensure_admin()
    return c


def ensure_viewer(server: ServerUnderTest) -> None:
    """Seed the viewer ``bob`` while the server is stopped (restarts it on a new port)."""

    with seed.stopped(server) as conn:
        if not seed.scalar(conn, "SELECT COUNT(*) FROM users WHERE username = ?", (VIEWER_USERNAME,)):
            seed.insert_user(conn, username=VIEWER_USERNAME, password=VIEWER_PASSWORD, role="viewer")


def signed_in_viewer(server: ServerUnderTest, client_factory: Callable[..., WeirClient]) -> WeirClient:
    c = client_factory(server)
    c.login(VIEWER_USERNAME, VIEWER_PASSWORD)
    return c


def delete_with_body_csrf(c: WeirClient, path: str) -> httpx.Response:
    """DELETE carrying ``csrf_token`` in a JSON body, the shape the Refiner delete routes take."""

    return c.request("DELETE", path, json={"csrf_token": c.csrf()})


def insert_job(
    conn: Any,
    *,
    dedupe_key: str,
    job_kind: str = REMUX_PASS_JOB_KIND,
    status: str = "pending",
    payload: dict[str, Any] | None = None,
) -> int:
    now = seed.utc_text()
    cur = conn.execute(
        "INSERT INTO refiner_jobs (dedupe_key, job_kind, payload_json, status, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (dedupe_key, job_kind, json.dumps(payload or {}), status, now, now),
    )
    return int(cur.lastrowid or 0)


def first_library_id(conn: Any) -> int:
    return int(seed.scalar(conn, "SELECT id FROM refiner_libraries ORDER BY id LIMIT 1"))


def insert_file(conn: Any, *, library_id: int, relative_path: str, **columns: Any) -> int:
    now = seed.utc_text()
    values: dict[str, Any] = {
        "library_id": library_id,
        "relative_path": relative_path,
        "status": "unprocessed",
        "status_reason": "",
        "created_at": now,
        "updated_at": now,
        **columns,
    }
    names = ", ".join(values)
    marks = ", ".join("?" for _ in values)
    cur = conn.execute(f"INSERT INTO refiner_files ({names}) VALUES ({marks})", tuple(values.values()))  # noqa: S608
    return int(cur.lastrowid or 0)
