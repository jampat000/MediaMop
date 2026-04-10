"""SQLite-first foundation: path resolution and connection PRAGMAs."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from mediamop.core.config import MediaMopSettings
from mediamop.core.db import create_db_engine, verify_sqlite_pragmas


def test_settings_sqlite_url_points_under_mediamop_home(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("MEDIAMOP_HOME", str(tmp_path))
    monkeypatch.delenv("MEDIAMOP_DB_PATH", raising=False)
    s = MediaMopSettings.load()
    assert s.sqlalchemy_database_url.startswith("sqlite:///")
    assert "mediamop.sqlite3" in s.sqlalchemy_database_url
    assert Path(s.db_path).resolve() == (tmp_path / "data" / "mediamop.sqlite3").resolve()


def test_engine_applies_sqlite_hardening_pragmas(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("MEDIAMOP_HOME", str(tmp_path))
    monkeypatch.delenv("MEDIAMOP_DB_PATH", raising=False)
    settings = MediaMopSettings.load()
    engine = create_db_engine(settings)
    try:
        p = verify_sqlite_pragmas(engine)
        assert p["journal_mode"].lower() == "wal"
        assert p["foreign_keys"] == "1"
        assert int(p["busy_timeout"]) == 5000
        assert p["synchronous"] == "1"
    finally:
        engine.dispose()
