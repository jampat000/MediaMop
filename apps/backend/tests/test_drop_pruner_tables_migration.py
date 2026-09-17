"""Migration 0036 removes Pruner's tables, and a fresh install never has them (#473).

Pruner moved to Deluno. ``0001`` builds from live ORM metadata, so a fresh database never
creates the tables; a database from an older install does have them, and 0036 has to
drop them — children first — without touching anything that stays.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.config import Config

from alembic import command
from mediamop.core.config import MediaMopSettings
from mediamop.core.db import create_db_engine

_BEFORE = "0035_direct_play_facts"


def _config(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, name: str) -> Config:
    monkeypatch.setenv("MEDIAMOP_SESSION_SECRET", "pytest-session-secret-32-chars-min!!")
    home = tmp_path / name
    home.mkdir()
    monkeypatch.setenv("MEDIAMOP_HOME", str(home))
    MediaMopSettings.load()
    backend = Path(__file__).resolve().parents[1]
    monkeypatch.chdir(backend)
    return Config(str(backend / "alembic.ini"))


def _pruner_tables(engine: sa.Engine) -> set[str]:
    return {t for t in sa.inspect(engine).get_table_names() if t.startswith("pruner_")}


def _create_legacy_pruner_tables(engine: sa.Engine) -> None:
    """The four tables as an older install had them, foreign keys included."""

    with engine.begin() as conn:
        conn.execute(sa.text("create table pruner_jobs (id integer primary key, job_kind text not null)"))
        conn.execute(sa.text("create table pruner_server_instances (id integer primary key, provider text not null)"))
        conn.execute(
            sa.text(
                "create table pruner_preview_runs (id integer primary key,"
                " server_instance_id integer not null references pruner_server_instances(id) on delete cascade,"
                " pruner_job_id integer references pruner_jobs(id) on delete set null)"
            )
        )
        conn.execute(
            sa.text(
                "create table pruner_scope_settings (id integer primary key,"
                " server_instance_id integer not null references pruner_server_instances(id) on delete cascade,"
                " last_preview_run_id integer references pruner_preview_runs(id) on delete set null)"
            )
        )
        conn.execute(sa.text("insert into pruner_jobs (id, job_kind) values (1, 'pruner.preview.v1')"))
        conn.execute(sa.text("insert into pruner_server_instances (id, provider) values (1, 'jellyfin')"))
        conn.execute(
            sa.text("insert into pruner_preview_runs (id, server_instance_id, pruner_job_id) values (1, 1, 1)")
        )
        conn.execute(
            sa.text("insert into pruner_scope_settings (id, server_instance_id, last_preview_run_id) values (1, 1, 1)")
        )


def test_fresh_install_has_no_pruner_tables(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    cfg = _config(monkeypatch, tmp_path, "fresh")
    command.upgrade(cfg, "head")

    assert _pruner_tables(create_db_engine(MediaMopSettings.load())) == set()


def test_upgrade_drops_pruner_tables_and_keeps_everything_else(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    cfg = _config(monkeypatch, tmp_path, "legacy")
    command.upgrade(cfg, _BEFORE)

    engine = create_db_engine(MediaMopSettings.load())
    _create_legacy_pruner_tables(engine)
    assert len(_pruner_tables(engine)) == 4
    tables_before = set(sa.inspect(engine).get_table_names())
    engine.dispose()

    command.upgrade(cfg, "head")

    engine = create_db_engine(MediaMopSettings.load())
    assert _pruner_tables(engine) == set()
    assert set(sa.inspect(engine).get_table_names()) == tables_before - {
        "pruner_jobs",
        "pruner_server_instances",
        "pruner_preview_runs",
        "pruner_scope_settings",
    }
    with engine.connect() as conn:
        assert conn.execute(sa.text("select count(*) from suite_settings")).scalar_one() == 1
