"""Refiner resolves configuration by library, and an unmigrated payload still works.

ADR-0014 §5 makes ``library_id`` additive rather than a new job-kind version, because a
version bump would strand every row already queued at upgrade time — and the queue is
exactly where a half-finished remux lives.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

import mediamop.modules.refiner.jobs_model  # noqa: F401
import mediamop.modules.refiner.refiner_library_model  # noqa: F401
import mediamop.modules.refiner.refiner_path_settings_model  # noqa: F401
import mediamop.platform.media_managers.connection_model  # noqa: F401
from mediamop.core.config import MediaMopSettings
from mediamop.core.db import Base
from mediamop.modules.refiner.refiner_library_model import (
    RefinerLibraryManagerLinkRow,
    RefinerLibraryRow,
    RefinerRuleSetRow,
)
from mediamop.modules.refiner.refiner_library_service import (
    admission_rules_for,
    manager_connection_ids_for,
    resolve_library,
    rules_config_for,
    seeded_library_for_scope,
)
from mediamop.modules.refiner.refiner_path_settings_service import resolve_refiner_path_runtime_for_remux
from mediamop.platform.media_managers.connection_model import MediaManagerConnectionRow


@pytest.fixture
def session(tmp_path: Path) -> Session:
    engine = create_engine(
        f"sqlite:///{tmp_path / 'libs.sqlite'}",
        connect_args={"check_same_thread": False},
        future=True,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, class_=Session, autoflush=False, autocommit=False, future=True)()


def _library(session: Session, tmp_path: Path, **overrides) -> RefinerLibraryRow:
    name = overrides.pop("name", "Movies")
    folder = tmp_path / name.replace(" ", "_")
    for sub in ("watched", "work", "output"):
        (folder / sub).mkdir(parents=True, exist_ok=True)
    row = RefinerLibraryRow(
        name=name,
        media_scope=overrides.pop("media_scope", "movie"),
        watched_folder=str(folder / "watched"),
        work_folder=str(folder / "work"),
        output_folder=str(folder / "output"),
        media_extensions_csv=".mkv,.mp4",
        exclude_markers_csv="__admin__,.sabnzbd",
        **overrides,
    )
    session.add(row)
    session.commit()
    return row


def test_a_payload_without_a_library_id_resolves_to_the_seeded_library(session: Session, tmp_path: Path) -> None:
    """The compatibility hinge: work queued before the upgrade must not be stranded."""

    movies = _library(session, tmp_path, name="Movies", media_scope="movie", display_order=0)
    tv = _library(session, tmp_path, name="TV", media_scope="tv", display_order=1)

    assert resolve_library(session, library_id=None, media_scope="movie") is movies
    assert resolve_library(session, library_id=None, media_scope="tv") is tv
    # An id that no longer exists falls back rather than failing the job outright.
    assert resolve_library(session, library_id=9999, media_scope="tv") is tv


def test_a_payload_with_a_library_id_uses_that_library(session: Session, tmp_path: Path) -> None:
    _library(session, tmp_path, name="Movies", media_scope="movie", display_order=0)
    fourk = _library(session, tmp_path, name="Movies 4K", media_scope="movie", display_order=1)

    assert resolve_library(session, library_id=fourk.id, media_scope="movie") is fourk
    # And the seeded one is still what a payload without an id gets.
    assert seeded_library_for_scope(session, "movie").name == "Movies"


def test_a_third_library_resolves_its_own_paths(session: Session, tmp_path: Path) -> None:
    """The whole point: a library beyond the seeded two processes independently."""

    _library(session, tmp_path, name="Movies", media_scope="movie", display_order=0)
    kids = _library(session, tmp_path, name="Kids", media_scope="movie", display_order=2)
    settings = MediaMopSettings.load()

    runtime, err = resolve_refiner_path_runtime_for_remux(session, settings, media_scope="movie", library_id=kids.id)

    assert err is None, err
    assert runtime is not None
    assert runtime.watched_folder == str(Path(kids.watched_folder))
    assert runtime.output_folder == str(Path(kids.output_folder))


def test_admission_rules_come_from_the_row_not_a_module_constant(session: Session, tmp_path: Path) -> None:
    library = _library(session, tmp_path, name="Movies")
    library.media_extensions_csv = ".mkv,.avi"
    library.exclude_markers_csv = "__admin__,staging"
    library.min_file_size_mb = 500
    library.top_level_only = True
    session.commit()

    rules = admission_rules_for(library)

    assert rules.media_extensions == frozenset({".mkv", ".avi"})
    assert rules.exclude_markers == frozenset({"__admin__", "staging"})
    assert rules.min_file_size_mb == 500
    assert rules.top_level_only is True


def test_two_libraries_can_share_one_rule_set(session: Session, tmp_path: Path) -> None:
    """ADR-0014 §3: changing shared handling once should change both."""

    rule_set = RefinerRuleSetRow(name="Shared", primary_audio_lang="jpn", subtitle_mode="remove_all")
    session.add(rule_set)
    session.commit()

    a = _library(session, tmp_path, name="Anime", rule_set_id=rule_set.id)
    b = _library(session, tmp_path, name="Anime 4K", rule_set_id=rule_set.id)

    assert rules_config_for(session, a).primary_audio_lang == "jpn"
    assert rules_config_for(session, b).primary_audio_lang == "jpn"

    rule_set.primary_audio_lang = "eng"
    session.commit()
    assert rules_config_for(session, a).primary_audio_lang == "eng"
    assert rules_config_for(session, b).primary_audio_lang == "eng"


def test_a_library_names_its_manager_connections(session: Session, tmp_path: Path) -> None:
    """The scope-to-kind inference is retired; a library states which managers cover it."""

    library = _library(session, tmp_path, name="Movies")
    for kind, name in (("radarr", "Radarr 1080p"), ("radarr", "Radarr 4K")):
        session.add(MediaManagerConnectionRow(kind=kind, name=name, base_url="http://h", api_key_ciphertext="c"))
    session.commit()
    ids = [row.id for row in session.query(MediaManagerConnectionRow).all()]
    for cid in ids:
        session.add(RefinerLibraryManagerLinkRow(library_id=library.id, connection_id=cid))
    session.commit()

    # Multiple connections are permitted and are the edge case, not an error.
    assert manager_connection_ids_for(session, library) == tuple(sorted(ids))


def test_a_library_with_no_named_manager_reports_none(session: Session, tmp_path: Path) -> None:
    library = _library(session, tmp_path, name="Movies")
    assert manager_connection_ids_for(session, library) == ()


def test_an_unconfigured_library_refuses_and_says_where_to_set_it(session: Session, tmp_path: Path) -> None:
    library = _library(session, tmp_path, name="Movies")
    library.watched_folder = ""
    session.commit()
    settings = MediaMopSettings.load()

    runtime, err = resolve_refiner_path_runtime_for_remux(session, settings, media_scope="movie", library_id=library.id)

    assert runtime is None
    assert err is not None
    assert "watched folder" in err.lower()
    assert "libraries" in err.lower()


def test_the_seeded_library_wins_over_a_later_one_for_a_scopeless_payload(session: Session, tmp_path: Path) -> None:
    """Display order decides, so adding a library never repoints existing queued work."""

    first = _library(session, tmp_path, name="Movies", display_order=0)
    _library(session, tmp_path, name="Movies 4K", display_order=5)

    assert resolve_library(session, library_id=None, media_scope="movie") is first


def test_settings_unchanged_when_no_library_covers_the_scope(session: Session, tmp_path: Path) -> None:
    """An unmigrated database falls back to the singleton rather than refusing all work."""

    from mediamop.modules.refiner.refiner_path_settings_model import RefinerPathSettingsRow

    watched = tmp_path / "legacy" / "watched"
    output = tmp_path / "legacy" / "output"
    watched.mkdir(parents=True)
    output.mkdir(parents=True)
    session.add(
        RefinerPathSettingsRow(
            id=1,
            refiner_watched_folder=str(watched),
            refiner_output_folder=str(output),
        )
    )
    session.commit()
    settings = replace(MediaMopSettings.load(), mediamop_home=str(tmp_path / "home"))

    runtime, err = resolve_refiner_path_runtime_for_remux(session, settings, media_scope="movie")

    assert err is None, err
    assert runtime is not None
    assert runtime.watched_folder == str(watched)
