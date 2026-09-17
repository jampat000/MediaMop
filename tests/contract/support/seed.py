"""Reading and writing the SQLite file while the server is **stopped**.

The contract is the HTTP API *and* the SQLite schema (ADR-0017), so a test may seed rows the API
has no way to create, or assert on rows the API never shows. Both happen only while no server
holds the file: :func:`stopped` stops the server, yields a connection, and starts it again.

Everything here is plain SQL against the shared schema. Nothing imports Weir.
"""

from __future__ import annotations

import contextlib
import sqlite3
from collections.abc import Iterator, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from tests.contract.support.launcher import ServerUnderTest


def connect(db_path: Path) -> sqlite3.Connection:
    if not db_path.is_file():
        raise FileNotFoundError(f"No Weir database at {db_path}; start the server (or migrate) first.")
    conn = sqlite3.connect(str(db_path), timeout=10.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


@contextlib.contextmanager
def stopped(server: ServerUnderTest, *, restart: bool = True) -> Iterator[sqlite3.Connection]:
    """Stop the server, hand out a connection, commit, and start the server again."""

    was_running = server.running
    server.stop()
    conn = connect(server.db_path)
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()
    if restart and was_running:
        server.start()


def rows(conn: sqlite3.Connection, sql: str, params: Sequence[Any] = ()) -> list[dict[str, Any]]:
    return [dict(r) for r in conn.execute(sql, tuple(params)).fetchall()]


def scalar(conn: sqlite3.Connection, sql: str, params: Sequence[Any] = ()) -> Any:
    row = conn.execute(sql, tuple(params)).fetchone()
    return None if row is None else row[0]


def utc_text(moment: datetime | None = None) -> str:
    """A timestamp in the shape the schema stores (``YYYY-MM-DD HH:MM:SS.ffffff``, UTC)."""

    value = (moment or datetime.now(UTC)).astimezone(UTC).replace(tzinfo=None)
    return value.isoformat(sep=" ")


def hash_password(plain: str) -> str:
    """An Argon2id PHC string, the format ``users.password_hash`` holds (ADR-0003)."""

    from argon2 import PasswordHasher

    return PasswordHasher(time_cost=3, memory_cost=65_536, parallelism=1, hash_len=32, salt_len=16).hash(plain)


def insert_user(
    conn: sqlite3.Connection,
    *,
    username: str,
    password: str,
    role: str = "viewer",
    is_active: bool = True,
) -> int:
    now = utc_text()
    cur = conn.execute(
        "INSERT INTO users (username, password_hash, role, is_active, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
        (username, hash_password(password), role, 1 if is_active else 0, now, now),
    )
    return int(cur.lastrowid or 0)


def insert_activity_event(
    conn: sqlite3.Connection,
    *,
    event_type: str,
    module: str,
    title: str,
    detail: str | None = None,
    created_at: datetime | None = None,
) -> int:
    cur = conn.execute(
        "INSERT INTO activity_events (event_type, module, title, detail, created_at) VALUES (?, ?, ?, ?, ?)",
        (event_type, module, title, detail, utc_text(created_at)),
    )
    return int(cur.lastrowid or 0)
