"""Which managers look after a scope — N connections, not one picked by product name."""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

import mediamop.platform.media_managers.connection_model  # noqa: F401
from mediamop.core.config import MediaMopSettings
from mediamop.core.db import Base
from mediamop.platform.arr_library.arr_connection_crypto import encrypt_arr_api_key
from mediamop.platform.media_managers.connection_model import MediaManagerConnectionRow
from mediamop.platform.media_managers.manager_binding import (
    collect_library_truth,
    collect_queue_signals,
    connections_for_scope,
)
from mediamop.platform.media_managers.manager_port import (
    ALL_MEDIA_SCOPES,
    ManagerCapabilities,
    ManagerLibraryTruth,
    ManagerQueueRow,
    ManagerQueueSignal,
)

_BINDING = "mediamop.platform.media_managers.manager_binding"


@pytest.fixture
def settings(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> MediaMopSettings:
    monkeypatch.setenv("MEDIAMOP_HOME", str(tmp_path))
    monkeypatch.setenv("MEDIAMOP_SESSION_SECRET", "session-secret-abcdefghijklmnopqrstuvwxyz")
    monkeypatch.setenv("MEDIAMOP_CREDENTIALS_SECRET", "credentials-secret")
    monkeypatch.delenv("MEDIAMOP_ARR_RADARR_BASE_URL", raising=False)
    monkeypatch.delenv("MEDIAMOP_ARR_RADARR_API_KEY", raising=False)
    monkeypatch.delenv("MEDIAMOP_ARR_SONARR_BASE_URL", raising=False)
    monkeypatch.delenv("MEDIAMOP_ARR_SONARR_API_KEY", raising=False)
    return MediaMopSettings.load()


@pytest.fixture
def session(tmp_path: Path) -> Session:
    engine = create_engine(
        f"sqlite:///{tmp_path / 'binding.sqlite'}",
        connect_args={"check_same_thread": False},
        future=True,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, class_=Session, autoflush=False, autocommit=False, future=True)()


def _add(
    session: Session,
    settings: MediaMopSettings,
    *,
    kind: str,
    name: str,
    enabled: bool = True,
    base_url: str = "http://manager.local",
    api_key: str | None = "key",
) -> MediaManagerConnectionRow:
    row = MediaManagerConnectionRow(
        kind=kind,
        name=name,
        enabled=enabled,
        base_url=base_url,
        api_key_ciphertext=encrypt_arr_api_key(settings, api_key) if api_key else None,
    )
    session.add(row)
    session.commit()
    return row


def test_a_library_can_be_served_by_more_than_one_connection(session: Session, settings: MediaMopSettings) -> None:
    _add(session, settings, kind="radarr", name="1080p")
    _add(session, settings, kind="radarr", name="4K")
    labels = [c.label for c in connections_for_scope(session, settings, media_scope="movie")]
    assert labels == ["Radarr (1080p)", "Radarr (4K)"]


def test_a_manager_serving_both_scopes_answers_for_both(session: Session, settings: MediaMopSettings) -> None:
    _add(session, settings, kind="deluno", name="Main")
    assert [c.label for c in connections_for_scope(session, settings, media_scope="movie")] == ["Deluno (Main)"]
    assert [c.label for c in connections_for_scope(session, settings, media_scope="tv")] == ["Deluno (Main)"]


def test_radarr_and_deluno_are_both_consulted_for_movies(session: Session, settings: MediaMopSettings) -> None:
    """The migration case the single-pick resolver could not express."""

    _add(session, settings, kind="radarr", name="Legacy")
    _add(session, settings, kind="deluno", name="Main")
    labels = [c.label for c in connections_for_scope(session, settings, media_scope="movie")]
    assert labels == ["Radarr (Legacy)", "Deluno (Main)"]


def test_a_sonarr_connection_is_not_asked_about_movies(session: Session, settings: MediaMopSettings) -> None:
    _add(session, settings, kind="sonarr", name="Main")
    assert connections_for_scope(session, settings, media_scope="movie") == []
    assert len(connections_for_scope(session, settings, media_scope="tv")) == 1


def test_a_disabled_connection_is_not_consulted(session: Session, settings: MediaMopSettings) -> None:
    _add(session, settings, kind="radarr", name="Off", enabled=False)
    assert connections_for_scope(session, settings, media_scope="movie") == []


def test_a_connection_with_no_saved_key_cannot_be_asked(session: Session, settings: MediaMopSettings) -> None:
    _add(session, settings, kind="radarr", name="Half", api_key=None)
    assert connections_for_scope(session, settings, media_scope="movie") == []


def test_environment_credentials_still_work_when_nothing_claims_the_scope(
    session: Session,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("MEDIAMOP_HOME", str(tmp_path))
    monkeypatch.setenv("MEDIAMOP_ARR_RADARR_BASE_URL", "http://radarr.local")
    monkeypatch.setenv("MEDIAMOP_ARR_RADARR_API_KEY", "env-key")
    env_settings = MediaMopSettings.load()
    resolved = connections_for_scope(session, env_settings, media_scope="movie")
    assert [c.kind for c in resolved] == ["radarr"]
    assert resolved[0].connection_id is None


def test_a_configured_connection_wins_over_the_environment(
    session: Session,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("MEDIAMOP_HOME", str(tmp_path))
    monkeypatch.setenv("MEDIAMOP_SESSION_SECRET", "session-secret-abcdefghijklmnopqrstuvwxyz")
    monkeypatch.setenv("MEDIAMOP_CREDENTIALS_SECRET", "credentials-secret")
    monkeypatch.setenv("MEDIAMOP_ARR_RADARR_BASE_URL", "http://radarr.local")
    monkeypatch.setenv("MEDIAMOP_ARR_RADARR_API_KEY", "env-key")
    env_settings = MediaMopSettings.load()
    _add(session, env_settings, kind="radarr", name="4K")
    resolved = connections_for_scope(session, env_settings, media_scope="movie")
    assert [c.label for c in resolved] == ["Radarr (4K)"]


def test_a_half_configured_row_is_a_deliberate_answer_not_a_fallback_to_the_environment(
    session: Session,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("MEDIAMOP_HOME", str(tmp_path))
    monkeypatch.setenv("MEDIAMOP_SESSION_SECRET", "session-secret-abcdefghijklmnopqrstuvwxyz")
    monkeypatch.setenv("MEDIAMOP_CREDENTIALS_SECRET", "credentials-secret")
    monkeypatch.setenv("MEDIAMOP_ARR_RADARR_BASE_URL", "http://radarr.local")
    monkeypatch.setenv("MEDIAMOP_ARR_RADARR_API_KEY", "env-key")
    env_settings = MediaMopSettings.load()
    _add(session, env_settings, kind="radarr", name="Half", api_key=None)
    assert connections_for_scope(session, env_settings, media_scope="movie") == []


def test_fan_out_asks_every_connection_covering_the_scope(
    session: Session,
    settings: MediaMopSettings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _add(session, settings, kind="radarr", name="1080p")
    _add(session, settings, kind="deluno", name="Main")
    asked: list[str] = []

    class _Port:
        def capabilities(self):
            return ManagerCapabilities(
                scopes=ALL_MEDIA_SCOPES,
                reports_queue=True,
                reports_library_truth=True,
                summary="stub",
            )

        def queue_rows(self, connection):
            asked.append(connection.label)
            return ManagerQueueSignal(connection=connection, status="reported")

        def library_truth(self, connection, *, media_scope):
            asked.append(f"{connection.label}:truth")
            return ManagerLibraryTruth(connection=connection, status="reported")

    monkeypatch.setattr(f"{_BINDING}.port_for_kind", lambda _kind: _Port())
    signals = collect_queue_signals(session, settings, media_scope="movie")
    assert len(signals) == 2
    assert asked == ["Radarr (1080p)", "Deluno (Main)"]

    asked.clear()
    truths = collect_library_truth(session, settings, media_scope="movie")
    assert len(truths) == 2
    assert asked == ["Radarr (1080p):truth", "Deluno (Main):truth"]


def test_a_both_scopes_manager_only_answers_about_the_scope_it_was_asked(
    session: Session,
    settings: MediaMopSettings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The manager reports its whole instance; the fan-out asked about one library."""

    _add(session, settings, kind="deluno", name="Main")

    class _Port:
        def capabilities(self):
            return ManagerCapabilities(
                scopes=ALL_MEDIA_SCOPES,
                reports_queue=True,
                reports_library_truth=False,
                summary="stub",
            )

        def queue_rows(self, connection):
            return ManagerQueueSignal(
                connection=connection,
                status="reported",
                rows=(
                    ManagerQueueRow(scope="movie", payload={"title": "a film"}),
                    ManagerQueueRow(scope="tv", payload={"title": "an episode"}),
                ),
            )

        def library_truth(self, connection, *, media_scope):
            return ManagerLibraryTruth(connection=connection, status="no_signal")

    monkeypatch.setattr(f"{_BINDING}.port_for_kind", lambda _kind: _Port())

    movies = collect_queue_signals(session, settings, media_scope="movie")
    assert [(r.scope, r.payload["title"]) for r in movies[0].rows] == [("movie", "a film")]

    tv = collect_queue_signals(session, settings, media_scope="tv")
    assert [(r.scope, r.payload["title"]) for r in tv[0].rows] == [("tv", "an episode")]


def test_filtering_rows_leaves_a_silent_manager_silent(
    session: Session,
    settings: MediaMopSettings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Dropping out-of-scope rows must not turn "could not ask" into "nothing is importing"."""

    _add(session, settings, kind="deluno", name="Main")

    class _Port:
        def capabilities(self):
            return ManagerCapabilities(
                scopes=ALL_MEDIA_SCOPES,
                reports_queue=True,
                reports_library_truth=False,
                summary="stub",
            )

        def queue_rows(self, connection):
            return ManagerQueueSignal(connection=connection, status="unreachable", detail="down")

        def library_truth(self, connection, *, media_scope):
            return ManagerLibraryTruth(connection=connection, status="no_signal")

    monkeypatch.setattr(f"{_BINDING}.port_for_kind", lambda _kind: _Port())
    signal = collect_queue_signals(session, settings, media_scope="movie")[0]
    assert signal.status == "unreachable"
    assert signal.detail == "down"
