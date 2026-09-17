"""Port of apps/backend/tests/test_alembic_revision_startup.py (schema revision checks at startup)."""

from __future__ import annotations

import sqlite3
import subprocess
from typing import Any

import pytest

from tests.contract.support import launcher, seed

# The first schema revision a released Weir wrote. A database left at it is "known, but behind".
OLDEST_RELEASED_REVISION = "0001_weir_initial_schema"


def _schema(conn: sqlite3.Connection) -> dict[str, set[str]]:
    tables = [r["name"] for r in seed.rows(conn, "SELECT name FROM sqlite_master WHERE type = 'table'")]
    return {t: {c["name"] for c in seed.rows(conn, f'PRAGMA table_info("{t}")')} for t in tables}


def _revision(conn: sqlite3.Connection) -> Any:
    return seed.scalar(conn, "SELECT version_num FROM alembic_version")


@pytest.fixture(scope="module")
def head_schema(server) -> dict[str, set[str]]:
    """Tables and columns of a data folder the server under test brought to its current schema."""

    with seed.stopped(server) as conn:
        return _schema(conn)


def test_ensure_database_at_application_head_ok_on_migrated_db(server, client_factory) -> None:
    """A server restarted on its own, already current, database starts and leaves the revision alone."""

    with seed.stopped(server) as conn:
        before = _revision(conn)
    assert before
    assert client_factory(server).get("/health").status_code == 200
    with seed.stopped(server) as conn:
        assert _revision(conn) == before


def test_head_schema_no_longer_carries_the_refiner_singleton_settings_tables(head_schema) -> None:
    """The libraries are the only store now (#363).

    Asserted rather than assumed, because the whole point of dropping them was to end the
    two-stores drift hazard, and a table quietly recreated by a later migration would put
    it straight back.
    """

    assert "refiner_path_settings" not in head_schema
    assert "refiner_remux_rules_settings" not in head_schema


def test_head_schema_carries_the_libraries_that_replaced_them(head_schema) -> None:
    assert "refiner_libraries" in head_schema
    library_columns = head_schema["refiner_libraries"]
    for name in ("watched_folder", "work_folder", "output_folder", "scan_interval_seconds"):
        assert name in library_columns

    assert "refiner_rule_sets" in head_schema
    rule_set_columns = head_schema["refiner_rule_sets"]
    assert "primary_audio_lang" in rule_set_columns
    assert "subtitle_mode" in rule_set_columns


def test_head_schema_includes_suite_settings_table(head_schema) -> None:
    assert "suite_settings" in head_schema
    names = head_schema["suite_settings"]
    assert "product_display_name" in names
    assert "signed_in_home_notice" in names
    assert "application_logs_enabled" not in names
    assert "configuration_backup_enabled" in names
    assert "configuration_backup_interval_hours" in names
    assert "configuration_backup_preferred_time" in names


def test_head_schema_includes_arr_library_operator_settings_table(head_schema) -> None:
    assert "arr_library_operator_settings" in head_schema
    names = head_schema["arr_library_operator_settings"]
    assert "sonarr_missing_search_enabled" in names
    assert "radarr_upgrade_search_schedule_interval_seconds" in names


def test_api_startup_fails_without_migrations(server_factory) -> None:
    """A data folder whose database has never been migrated: the server refuses to start and changes nothing."""

    sut = server_factory(start=False)
    sut.db_path.parent.mkdir(parents=True, exist_ok=True)
    sqlite3.connect(str(sut.db_path)).close()  # an empty, unversioned SQLite file

    with pytest.raises(RuntimeError):
        sut.start(timeout_s=60)
    assert not sut.running

    conn = seed.connect(sut.db_path)
    try:
        assert seed.rows(conn, "SELECT name FROM sqlite_master WHERE type = 'table'") == []
    finally:
        conn.close()


def test_api_startup_auto_upgrades_known_behind_revision_to_head(server, server_factory, client_factory) -> None:
    """A database an older release left at its first schema revision is upgraded when the server starts."""

    with seed.stopped(server) as conn:
        head = _revision(conn)

    sut = server_factory(start=False)
    sut.home.mkdir(parents=True, exist_ok=True)
    # Build the older release's database with the released migration tool, not the server under test.
    result = subprocess.run(
        [launcher.python_executable(), "-m", "alembic", "upgrade", OLDEST_RELEASED_REVISION],
        cwd=str(launcher.BACKEND_DIR),
        env={**sut.environment(), "PYTHONPATH": str(launcher.BACKEND_DIR / "src")},
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, f"{result.stdout}\n{result.stderr}"
    conn = seed.connect(sut.db_path)
    try:
        assert _revision(conn) == OLDEST_RELEASED_REVISION
    finally:
        conn.close()

    sut.start()
    assert client_factory(sut).get("/health").status_code == 200

    with seed.stopped(sut, restart=False) as conn:
        assert _revision(conn) == head
