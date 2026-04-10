"""SQLite-first foundation: path resolution and connection PRAGMAs."""

from __future__ import annotations

import os
import stat
import sys
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


def test_db_path_existing_directory_rejected(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    mistake = home / "oops.sqlite3"
    mistake.mkdir()
    monkeypatch.setenv("MEDIAMOP_HOME", str(home))
    monkeypatch.setenv("MEDIAMOP_DB_PATH", "oops.sqlite3")
    with pytest.raises(RuntimeError, match="must be a file, not a directory"):
        MediaMopSettings.load()


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX directory modes; Windows owner semantics differ")
def test_db_parent_must_allow_new_file(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    home = tmp_path / "h"
    home.mkdir()
    locked = home / "locked"
    locked.mkdir()
    os.chmod(locked, stat.S_IRUSR | stat.S_IXUSR)
    monkeypatch.setenv("MEDIAMOP_HOME", str(home))
    monkeypatch.setenv("MEDIAMOP_DB_PATH", "locked/fresh.sqlite3")
    try:
        with pytest.raises(RuntimeError, match="Cannot create files under database directory"):
            MediaMopSettings.load()
    finally:
        os.chmod(locked, stat.S_IRWXU)


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX file modes; Windows owner semantics differ")
def test_existing_db_file_must_be_writable(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    home = tmp_path / "h"
    home.mkdir()
    db_f = home / "data" / "m.sqlite3"
    db_f.parent.mkdir(parents=True)
    db_f.write_bytes(b"")
    os.chmod(db_f, stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH)
    monkeypatch.setenv("MEDIAMOP_HOME", str(home))
    monkeypatch.setenv("MEDIAMOP_DB_PATH", str(db_f))
    try:
        with pytest.raises(RuntimeError, match="not writable"):
            MediaMopSettings.load()
    finally:
        os.chmod(db_f, stat.S_IRUSR | stat.S_IWUSR)
