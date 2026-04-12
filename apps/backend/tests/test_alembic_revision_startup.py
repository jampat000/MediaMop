"""Alembic head enforcement and safe auto-upgrade at API startup."""

from __future__ import annotations

from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from starlette.testclient import TestClient

from mediamop.api.factory import create_app
from mediamop.core.alembic_revision_check import DatabaseSchemaMismatch, ensure_database_at_application_head
from mediamop.core.config import MediaMopSettings
from mediamop.core.db import create_db_engine


def test_ensure_database_at_application_head_ok_on_migrated_db() -> None:
    settings = MediaMopSettings.load()
    engine = create_db_engine(settings)
    ensure_database_at_application_head(engine)


def test_head_schema_includes_refiner_path_settings_table() -> None:
    settings = MediaMopSettings.load()
    engine = create_db_engine(settings)
    insp = sa.inspect(engine)
    assert insp.has_table("refiner_path_settings")
    names = {c["name"] for c in insp.get_columns("refiner_path_settings")}
    assert "refiner_watched_folder" in names
    assert "refiner_work_folder" in names
    assert "refiner_output_folder" in names


def test_head_schema_includes_suite_settings_table() -> None:
    settings = MediaMopSettings.load()
    engine = create_db_engine(settings)
    insp = sa.inspect(engine)
    assert insp.has_table("suite_settings")
    names = {c["name"] for c in insp.get_columns("suite_settings")}
    assert "product_display_name" in names
    assert "signed_in_home_notice" in names


def test_api_startup_fails_without_migrations(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("MEDIAMOP_SESSION_SECRET", "pytest-session-secret-32-chars-min!!")
    isolated = tmp_path / "nodb"
    isolated.mkdir()
    monkeypatch.setenv("MEDIAMOP_HOME", str(isolated))
    MediaMopSettings.load()

    with pytest.raises(DatabaseSchemaMismatch) as excinfo:
        with TestClient(create_app()):
            pass
    assert excinfo.value.kind == "unversioned"


def test_unversioned_error_includes_cross_platform_migration_instructions(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("MEDIAMOP_SESSION_SECRET", "pytest-session-secret-32-chars-min!!")
    isolated = tmp_path / "empty_schema"
    isolated.mkdir()
    monkeypatch.setenv("MEDIAMOP_HOME", str(isolated))
    MediaMopSettings.load()
    eng = create_db_engine(MediaMopSettings.load())
    with pytest.raises(DatabaseSchemaMismatch) as excinfo:
        ensure_database_at_application_head(eng)
    msg = str(excinfo.value).lower()
    assert "alembic upgrade head" in msg
    assert "pythonpath=src" in msg or "pythonpath" in msg


def test_api_startup_auto_upgrades_known_behind_revision_to_head(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("MEDIAMOP_SESSION_SECRET", "pytest-session-secret-32-chars-min!!")
    home = tmp_path / "behind"
    home.mkdir()
    monkeypatch.setenv("MEDIAMOP_HOME", str(home))
    MediaMopSettings.load()

    backend = Path(__file__).resolve().parents[1]
    cfg = Config(str(backend / "alembic.ini"))
    monkeypatch.chdir(backend)
    command.upgrade(cfg, "0001_initial_auth")

    with TestClient(create_app()) as client:
        assert client.get("/health").status_code == 200

    settings = MediaMopSettings.load()
    engine = create_db_engine(settings)
    script = ScriptDirectory.from_config(cfg)
    head = script.get_heads()[0]
    with engine.connect() as conn:
        ctx = MigrationContext.configure(conn)
        assert ctx.get_current_revision() == head
