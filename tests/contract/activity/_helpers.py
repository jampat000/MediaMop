"""Shared helpers for the activity contract tests: seeding history rows and signing in."""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime, timedelta
from typing import Any

from tests.contract.support import seed
from tests.contract.support.client import WeirClient

VIEWER_USERNAME = "bob"
VIEWER_PASSWORD = "viewer-password-here"


def insert_event(
    conn: sqlite3.Connection,
    *,
    event_type: str,
    module: str,
    title: str,
    detail: dict[str, Any] | str | None = None,
    created_at: datetime | None = None,
    trigger: str | None = None,
    result: str | None = None,
    library_id: int | None = None,
    relative_path: str | None = None,
    run_key: str | None = None,
) -> int:
    """One ``activity_events`` row with its filterable facts, the way the server writes them (#469)."""

    text = json.dumps(detail) if isinstance(detail, dict) else detail
    cur = conn.execute(
        'INSERT INTO activity_events (event_type, module, title, detail, created_at, "trigger", result, '
        "library_id, relative_path, run_key) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            event_type,
            module,
            title,
            text,
            seed.utc_text(created_at),
            trigger,
            result,
            library_id,
            relative_path,
            run_key,
        ),
    )
    return int(cur.lastrowid or 0)


def ensure_viewer(conn: sqlite3.Connection) -> None:
    if seed.scalar(conn, "SELECT COUNT(*) FROM users WHERE username = ?", (VIEWER_USERNAME,)) == 0:
        seed.insert_user(conn, username=VIEWER_USERNAME, password=VIEWER_PASSWORD, role="viewer")


# The four Processing results the history tests filter on, with the facts the server lifts from each detail.
HISTORY_ROWS: tuple[tuple[str, dict[str, Any], dict[str, Any]], ...] = (
    (
        "Heat was handed back",
        {"trigger": "scheduled", "library_id": 1, "relative_media_path": "Heat/heat.mkv"},
        {"trigger": "scheduled", "result": "success", "library_id": 1, "relative_path": "Heat/heat.mkv"},
    ),
    (
        "Heat failed",
        {"trigger": "retry", "ok": False, "library_id": 1, "relative_media_path": "Heat/heat.mkv"},
        {"trigger": "retry", "result": "failed", "library_id": 1, "relative_path": "Heat/heat.mkv"},
    ),
    (
        "Alien processed",
        {"trigger": "manual", "library_id": 1, "relative_media_path": "Alien/alien.mkv"},
        {"trigger": "manual", "result": "success", "library_id": 1, "relative_path": "Alien/alien.mkv"},
    ),
    (
        "Show processed",
        {"trigger": "webhook", "library_id": 2, "relative_media_path": "Show/S01E01.mkv"},
        {"trigger": "webhook", "result": "success", "library_id": 2, "relative_path": "Show/S01E01.mkv"},
    ),
)


def seed_history(conn: sqlite3.Connection) -> None:
    """Replace all activity and per-file processing records with the four Processing results."""

    now = datetime.now(UTC)
    conn.execute("DELETE FROM activity_events")
    conn.execute("DELETE FROM file_logs")
    for offset, (title, detail, facts) in enumerate(HISTORY_ROWS):
        insert_event(
            conn,
            event_type="processing.file_remux_pass_completed",
            module="processing",
            title=title,
            detail=detail,
            created_at=now - timedelta(seconds=10 - offset),
            **facts,
        )
    for path in ("Heat/heat.mkv", "Alien/alien.mkv"):
        conn.execute(
            "INSERT INTO file_logs (library_id, relative_path, title, recorded_at) VALUES (?, ?, ?, ?)",
            (1, path, "pass", seed.utc_text(now)),
        )
    ensure_viewer(conn)


def signed_in(client: WeirClient, username: str | None = None, password: str | None = None) -> WeirClient:
    if username is None:
        client.ensure_admin()
    else:
        client.login(username, password or "")
    return client
