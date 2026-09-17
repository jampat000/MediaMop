"""Plain-SQL resets and seeds for the E2E suite. Nothing here imports Weir (the server is the .NET server).

Writes happen while the server runs, the same way an operator's second process would; the server does
not cache the rows touched here.
"""

from __future__ import annotations

import os
import sqlite3
from datetime import UTC, datetime
from pathlib import Path


def db_path_for_home(home: str) -> Path:
    """The SQLite file the server uses for ``home`` (``WEIR_DB_PATH``, relative to the home, or the default)."""

    configured = (os.environ.get("WEIR_DB_PATH") or "").strip()
    if configured:
        path = Path(configured)
        return path if path.is_absolute() else Path(home) / path
    return Path(home) / "data" / "weir.sqlite3"


def _connect(home: str) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path_for_home(home)), timeout=30)
    conn.execute("PRAGMA busy_timeout = 30000")
    return conn


def clear_auth_tables_for_home(home: str) -> None:
    """Reset all per-test state so each test starts from a clean baseline.

    Auth tables (users, user_sessions, suite_settings) are cleared so the next test begins at the
    setup / login page.

    Module configuration is also reset so that wizard skip and Refiner forms don't inherit stale
    paths from a previous test. The migration-seeded Refiner libraries have their folders *cleared*
    rather than being deleted, because they are the only path store now (#363) and a scope with no
    library at all has nowhere to resolve to.
    """

    conn = _connect(home)
    try:
        with conn:
            conn.execute("UPDATE refiner_libraries SET watched_folder = '', work_folder = '', output_folder = ''")
            conn.execute("DELETE FROM user_sessions")
            conn.execute("DELETE FROM users")
            conn.execute("DELETE FROM suite_settings")
    finally:
        conn.close()


def insert_activity_event(home: str, *, event_type: str, module: str, title: str, detail: str | None = None) -> None:
    """One ``activity_events`` row, stamped now in the stored shape (``YYYY-MM-DD HH:MM:SS.ffffff``, UTC)."""

    created_at = datetime.now(UTC).replace(tzinfo=None).isoformat(sep=" ", timespec="microseconds")
    conn = _connect(home)
    try:
        with conn:
            conn.execute(
                "INSERT INTO activity_events (created_at, event_type, module, title, detail) VALUES (?, ?, ?, ?, ?)",
                (created_at, event_type, module, title, detail or None),
            )
    finally:
        conn.close()
