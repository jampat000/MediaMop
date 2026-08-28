"""Migration 0011 seeds two libraries and changes nothing an operator can observe.

ADR-0014 §6 makes "upgrade is a behavioural no-op" the hard constraint, not a
nice-to-have: a library's watched folder is the input to source-folder deletion, so a
value that moves without the operator asking is destructive. These tests upgrade a
database that has *already been configured*, which is the only case where that can go
wrong — a fresh install has nothing to carry.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.config import Config

from alembic import command
from mediamop.core.config import MediaMopSettings
from mediamop.core.db import create_db_engine

_BEFORE = "0010_drop_subber_tables"


def _config(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, name: str) -> Config:
    monkeypatch.setenv("MEDIAMOP_SESSION_SECRET", "pytest-session-secret-32-chars-min!!")
    home = tmp_path / name
    home.mkdir()
    monkeypatch.setenv("MEDIAMOP_HOME", str(home))
    MediaMopSettings.load()
    backend = Path(__file__).resolve().parents[1]
    monkeypatch.chdir(backend)
    return Config(str(backend / "alembic.ini"))


def _engine() -> sa.Engine:
    return create_db_engine(MediaMopSettings.load())


def _rows(engine: sa.Engine, sql: str) -> list[dict]:
    with engine.connect() as conn:
        return [dict(r) for r in conn.execute(sa.text(sql)).mappings()]


def test_seed_carries_configured_paths_and_rules_verbatim(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    cfg = _config(monkeypatch, tmp_path, "configured")
    command.upgrade(cfg, _BEFORE)

    engine = _engine()
    with engine.begin() as conn:
        conn.execute(
            sa.text(
                "update refiner_path_settings set"
                " refiner_watched_folder = '/srv/movies/in',"
                " refiner_work_folder = '/srv/movies/work',"
                " refiner_output_folder = '/srv/movies/out',"
                " refiner_tv_watched_folder = '/srv/tv/in',"
                " refiner_tv_work_folder = '/srv/tv/work',"
                " refiner_tv_output_folder = '/srv/tv/out',"
                " movie_watched_folder_check_interval_seconds = 900,"
                " tv_watched_folder_check_interval_seconds = 120"
                " where id = 1"
            )
        )
        conn.execute(
            sa.text(
                "update refiner_remux_rules_settings set"
                " primary_audio_lang = 'jpn', subtitle_mode = 'keep_listed',"
                " subtitle_langs_csv = 'eng,jpn', remove_commentary = 1,"
                " tv_primary_audio_lang = 'deu', tv_subtitle_mode = 'remove_all',"
                " tv_remove_commentary = 0"
                " where id = 1"
            )
        )
        conn.execute(
            sa.text(
                "update refiner_operator_settings set"
                " min_file_age_seconds = 45, refiner_min_input_file_size_mb = 250,"
                " max_concurrent_files = 4,"
                " movie_schedule_enabled = 1, movie_schedule_hours_limited = 1,"
                " movie_schedule_days = 'Mon,Tue', movie_schedule_start = '01:00',"
                " movie_schedule_end = '05:00',"
                " tv_schedule_enabled = 0"
                " where id = 1"
            )
        )

    command.upgrade(cfg, "head")

    libraries = {r["name"]: r for r in _rows(_engine(), "select * from refiner_libraries")}
    assert set(libraries) == {"Movies", "TV"}

    movies = libraries["Movies"]
    assert movies["media_scope"] == "movie"
    assert movies["watched_folder"] == "/srv/movies/in"
    assert movies["work_folder"] == "/srv/movies/work"
    assert movies["output_folder"] == "/srv/movies/out"
    assert movies["scan_interval_seconds"] == 900
    # Guardrails were global; each seeded library inherits the same values.
    assert movies["min_file_age_seconds"] == 45
    assert movies["min_file_size_mb"] == 250
    assert movies["max_concurrent_files"] == 4
    assert movies["schedule_hours_limited"] == 1
    assert movies["schedule_days"] == "Mon,Tue"
    assert movies["schedule_start"] == "01:00"
    assert movies["schedule_end"] == "05:00"

    tv = libraries["TV"]
    assert tv["media_scope"] == "tv"
    assert tv["watched_folder"] == "/srv/tv/in"
    assert tv["output_folder"] == "/srv/tv/out"
    assert tv["scan_interval_seconds"] == 120
    assert tv["schedule_enabled"] == 0

    rule_sets = {r["id"]: r for r in _rows(_engine(), "select * from refiner_rule_sets")}
    movie_rules = rule_sets[movies["rule_set_id"]]
    assert movie_rules["primary_audio_lang"] == "jpn"
    assert movie_rules["subtitle_mode"] == "keep_listed"
    assert movie_rules["subtitle_langs_csv"] == "eng,jpn"
    assert movie_rules["remove_commentary"] == 1

    # The tv_-prefixed half of the singleton must land on the TV library, not the movie one.
    tv_rules = rule_sets[tv["rule_set_id"]]
    assert tv_rules["primary_audio_lang"] == "deu"
    assert tv_rules["subtitle_mode"] == "remove_all"
    assert tv_rules["remove_commentary"] == 0
    assert movies["rule_set_id"] != tv["rule_set_id"]


def test_seed_carries_the_former_module_constants_as_saved_values(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """The allowlist and staging markers become editable data without changing behaviour."""

    cfg = _config(monkeypatch, tmp_path, "constants")
    command.upgrade(cfg, "head")

    for row in _rows(_engine(), "select * from refiner_libraries"):
        extensions = row["media_extensions_csv"].split(",")
        assert ".mkv" in extensions
        assert ".mov" in extensions
        # Raw elementary streams stayed out of the allowlist in #348 and must stay out here.
        assert ".h264" not in extensions
        markers = row["exclude_markers_csv"].split(",")
        assert "__admin__" in markers
        assert ".sabnzbd" in markers


def test_seed_links_the_manager_the_retired_inference_would_have_chosen(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    cfg = _config(monkeypatch, tmp_path, "managers")
    command.upgrade(cfg, _BEFORE)

    engine = _engine()
    with engine.begin() as conn:
        for kind, name in (("radarr", "Radarr 4K"), ("sonarr", "Sonarr Main"), ("deluno", "Deluno")):
            conn.execute(
                sa.text(
                    "insert into media_manager_connections (kind, name, enabled, base_url, api_key_ciphertext)"
                    " values (:k, :n, 1, 'http://host', 'cipher')"
                ),
                {"k": kind, "n": name},
            )

    command.upgrade(cfg, "head")

    linked = _rows(
        _engine(),
        "select l.name as library, c.kind as kind from refiner_library_manager_links k"
        " join refiner_libraries l on l.id = k.library_id"
        " join media_manager_connections c on c.id = k.connection_id",
    )
    by_library = {r["library"]: r["kind"] for r in linked}
    # Exactly what {"movie": "radarr", "tv": "sonarr"} resolved to, so nothing moves.
    assert by_library == {"Movies": "radarr", "TV": "sonarr"}


def test_seed_falls_back_to_a_both_scopes_manager_when_no_arr_is_configured(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    cfg = _config(monkeypatch, tmp_path, "deluno-only")
    command.upgrade(cfg, _BEFORE)

    with _engine().begin() as conn:
        conn.execute(
            sa.text(
                "insert into media_manager_connections (kind, name, enabled, base_url, api_key_ciphertext)"
                " values ('deluno', 'Deluno', 1, 'http://host', 'cipher')"
            )
        )

    command.upgrade(cfg, "head")

    linked = _rows(
        _engine(),
        "select l.name as library, c.kind as kind from refiner_library_manager_links k"
        " join refiner_libraries l on l.id = k.library_id"
        " join media_manager_connections c on c.id = k.connection_id",
    )
    assert {r["library"]: r["kind"] for r in linked} == {"Movies": "deluno", "TV": "deluno"}


def test_a_half_configured_connection_is_not_linked(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Linking a connection with no saved key would claim a manager Refiner cannot ask."""

    cfg = _config(monkeypatch, tmp_path, "half")
    command.upgrade(cfg, _BEFORE)

    with _engine().begin() as conn:
        conn.execute(
            sa.text(
                "insert into media_manager_connections (kind, name, enabled, base_url, api_key_ciphertext)"
                " values ('radarr', 'Half', 1, 'http://host', NULL)"
            )
        )

    command.upgrade(cfg, "head")

    assert _rows(_engine(), "select * from refiner_library_manager_links") == []


def test_seeding_is_idempotent(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """A fresh database already has the tables from 0001, so 0011 must not double-seed."""

    cfg = _config(monkeypatch, tmp_path, "idempotent")
    command.upgrade(cfg, "head")
    assert len(_rows(_engine(), "select * from refiner_libraries")) == 2

    command.downgrade(cfg, _BEFORE)
    command.upgrade(cfg, "head")
    names = [r["name"] for r in _rows(_engine(), "select * from refiner_libraries")]
    assert sorted(names) == ["Movies", "TV"]


def test_the_singleton_rows_are_untouched_by_the_seed(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Step 8 drops them; until then they stay readable so every step has a rollback."""

    cfg = _config(monkeypatch, tmp_path, "untouched")
    command.upgrade(cfg, _BEFORE)
    with _engine().begin() as conn:
        conn.execute(sa.text("update refiner_path_settings set refiner_watched_folder = '/keep/me' where id = 1"))

    command.upgrade(cfg, "head")

    rows = _rows(_engine(), "select refiner_watched_folder from refiner_path_settings where id = 1")
    assert rows[0]["refiner_watched_folder"] == "/keep/me"
