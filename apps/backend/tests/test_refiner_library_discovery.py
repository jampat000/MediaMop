"""Libraries discovered from a manager, and the drift report that never applies itself.

Refiner deletes source folders after a successful pass, so a watched folder that
silently repoints is a destructive surprise. Every test here that touches a path asserts
MediaMop reported rather than moved it.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

import mediamop.modules.refiner.jobs_model  # noqa: F401
import mediamop.modules.refiner.refiner_library_model  # noqa: F401
import mediamop.platform.media_managers.connection_model  # noqa: F401
from mediamop.core.config import MediaMopSettings
from mediamop.core.db import Base
from mediamop.modules.refiner import refiner_library_discovery as discovery
from mediamop.modules.refiner.refiner_library_discovery import (
    RefinerDiscoveryError,
    discoverable_libraries,
    import_libraries,
    local_path_problem,
    resync_drift,
    unlink_library,
)
from mediamop.modules.refiner.refiner_library_model import RefinerLibraryRow
from mediamop.platform.media_managers.connection_model import MediaManagerConnectionRow
from mediamop.platform.media_managers.manager_port import ManagerLibraryDescriptor


@pytest.fixture
def session(tmp_path: Path) -> Session:
    engine = create_engine(
        f"sqlite:///{tmp_path / 'discovery.sqlite'}",
        connect_args={"check_same_thread": False},
        future=True,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, class_=Session, autoflush=False, autocommit=False, future=True)()


@pytest.fixture
def connection(session: Session) -> MediaManagerConnectionRow:
    row = MediaManagerConnectionRow(
        kind="deluno", name="Deluno", enabled=True, base_url="http://h", api_key_ciphertext="c"
    )
    session.add(row)
    session.commit()
    return row


def _reports(monkeypatch: pytest.MonkeyPatch, *descriptors: ManagerLibraryDescriptor) -> None:
    monkeypatch.setattr(discovery, "_descriptors_for", lambda _s, _c, _row: tuple(descriptors))


def _settings() -> MediaMopSettings:
    return MediaMopSettings.load()


def test_a_local_path_that_exists_has_no_problem(tmp_path: Path) -> None:
    assert local_path_problem(str(tmp_path)) is None


def test_a_path_the_manager_sees_but_mediamop_cannot_is_reported_with_both_values(tmp_path: Path) -> None:
    problem = local_path_problem("/srv/on-another-host/movies")
    assert problem is not None
    assert "/srv/on-another-host/movies" in problem
    assert "machine running" in problem


def test_a_missing_root_is_reported_rather_than_guessed() -> None:
    problem = local_path_problem(None)
    assert problem is not None
    assert "did not say where" in problem


def test_listing_marks_what_is_already_imported(
    session: Session, connection: MediaManagerConnectionRow, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _reports(
        monkeypatch,
        ManagerLibraryDescriptor(key="7", name="Films", media_scope="movie", root_path=str(tmp_path)),
        ManagerLibraryDescriptor(key="8", name="Shows", media_scope="tv", root_path=str(tmp_path)),
    )
    session.add(
        RefinerLibraryRow(
            name="Films", media_scope="movie", discovered_from_connection_id=connection.id, discovered_library_key="7"
        )
    )
    session.commit()

    found = {item.key: item for item in discoverable_libraries(session, _settings(), connection)}

    assert found["7"].already_imported is True
    assert found["8"].already_imported is False
    assert found["8"].media_scope == "tv"


def test_importing_a_subset_creates_only_what_was_chosen(
    session: Session, connection: MediaManagerConnectionRow, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _reports(
        monkeypatch,
        ManagerLibraryDescriptor(key="7", name="Films", media_scope="movie", root_path=str(tmp_path)),
        ManagerLibraryDescriptor(key="8", name="Shows", media_scope="tv", root_path=str(tmp_path)),
        ManagerLibraryDescriptor(key="9", name="Kids", media_scope="movie", root_path=str(tmp_path)),
    )

    created = import_libraries(session, _settings(), connection, keys=["7", "9"])
    session.commit()

    assert sorted(r.name for r in created) == ["Films", "Kids"]
    assert {r.discovered_library_key for r in created} == {"7", "9"}
    assert all(r.discovered_from_connection_id == connection.id for r in created)
    # The manager's root is adopted as the watched folder when MediaMop can see it.
    assert all(r.watched_folder == str(tmp_path) for r in created)


def test_an_imported_library_is_editable_afterwards(
    session: Session, connection: MediaManagerConnectionRow, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _reports(monkeypatch, ManagerLibraryDescriptor(key="7", name="Films", media_scope="movie", root_path=str(tmp_path)))
    created = import_libraries(session, _settings(), connection, keys=["7"])[0]
    session.commit()

    created.name = "Films renamed"
    created.min_file_size_mb = 700
    session.commit()

    reloaded = session.get(RefinerLibraryRow, created.id)
    assert reloaded is not None
    assert reloaded.name == "Films renamed"
    assert reloaded.min_file_size_mb == 700
    # Still linked, so a later re-sync can still report on it.
    assert reloaded.discovered_library_key == "7"


def test_a_root_mediamop_cannot_see_imports_without_a_watched_folder(
    session: Session, connection: MediaManagerConnectionRow, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Better an empty folder the operator fills in than one that fails every scan."""

    _reports(
        monkeypatch,
        ManagerLibraryDescriptor(key="7", name="Films", media_scope="movie", root_path="/srv/elsewhere"),
    )

    created = import_libraries(session, _settings(), connection, keys=["7"])[0]

    assert created.watched_folder == ""
    assert created.discovered_library_key == "7"


def test_a_duplicate_name_is_disambiguated_rather_than_refused(
    session: Session, connection: MediaManagerConnectionRow, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    session.add(RefinerLibraryRow(name="Films", media_scope="movie"))
    session.commit()
    _reports(monkeypatch, ManagerLibraryDescriptor(key="7", name="Films", media_scope="movie", root_path=str(tmp_path)))

    created = import_libraries(session, _settings(), connection, keys=["7"])[0]

    assert created.name == "Films (2)"


def test_importing_nothing_is_refused(
    session: Session, connection: MediaManagerConnectionRow, monkeypatch: pytest.MonkeyPatch
) -> None:
    _reports(monkeypatch)
    with pytest.raises(RefinerDiscoveryError):
        import_libraries(session, _settings(), connection, keys=[])


def test_resync_reports_a_moved_root_and_changes_nothing(
    session: Session, connection: MediaManagerConnectionRow, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The rule this feature turns on: a watched folder only moves when the operator moves it."""

    row = RefinerLibraryRow(
        name="Films",
        media_scope="movie",
        watched_folder=str(tmp_path / "old"),
        discovered_from_connection_id=connection.id,
        discovered_library_key="7",
    )
    session.add(row)
    session.commit()
    _reports(
        monkeypatch,
        ManagerLibraryDescriptor(key="7", name="Films", media_scope="movie", root_path=str(tmp_path / "new")),
    )

    drift = resync_drift(session, _settings(), connection)

    moved = [d for d in drift if d.kind == "root_moved"]
    assert len(moved) == 1
    assert moved[0].manager_value == str(tmp_path / "new")
    assert moved[0].mediamop_value == str(tmp_path / "old")
    # Nothing applied.
    session.refresh(row)
    assert row.watched_folder == str(tmp_path / "old")


def test_resync_reports_a_library_the_manager_no_longer_has(
    session: Session, connection: MediaManagerConnectionRow, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    row = RefinerLibraryRow(
        name="Gone",
        media_scope="movie",
        watched_folder=str(tmp_path),
        discovered_from_connection_id=connection.id,
        discovered_library_key="7",
    )
    session.add(row)
    session.commit()
    _reports(monkeypatch)

    drift = resync_drift(session, _settings(), connection)

    assert [d.kind for d in drift] == ["library_removed"]
    assert drift[0].library_id == row.id
    # Left exactly as it was.
    session.refresh(row)
    assert row.watched_folder == str(tmp_path)


def test_resync_reports_a_library_that_appeared(
    session: Session, connection: MediaManagerConnectionRow, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _reports(
        monkeypatch,
        ManagerLibraryDescriptor(key="9", name="New", media_scope="movie", root_path=str(tmp_path)),
    )

    drift = resync_drift(session, _settings(), connection)

    assert [d.kind for d in drift] == ["library_added"]
    assert drift[0].library_name == "New"
    # Reported only — nothing was created.
    assert session.query(RefinerLibraryRow).count() == 0


def test_resync_is_quiet_when_nothing_has_changed(
    session: Session, connection: MediaManagerConnectionRow, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    session.add(
        RefinerLibraryRow(
            name="Films",
            media_scope="movie",
            watched_folder=str(tmp_path),
            discovered_from_connection_id=connection.id,
            discovered_library_key="7",
        )
    )
    session.commit()
    _reports(monkeypatch, ManagerLibraryDescriptor(key="7", name="Films", media_scope="movie", root_path=str(tmp_path)))

    assert resync_drift(session, _settings(), connection) == []


def test_a_manual_library_is_never_reported_as_drift(
    session: Session, connection: MediaManagerConnectionRow, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Discovery is a convenience. A hand-made library is nobody's business but the operator's."""

    session.add(RefinerLibraryRow(name="Hand made", media_scope="movie", watched_folder=str(tmp_path / "mine")))
    session.commit()
    _reports(monkeypatch)

    assert resync_drift(session, _settings(), connection) == []


def test_unlinking_keeps_the_library(session: Session, connection: MediaManagerConnectionRow, tmp_path: Path) -> None:
    row = RefinerLibraryRow(
        name="Films",
        media_scope="movie",
        watched_folder=str(tmp_path),
        discovered_from_connection_id=connection.id,
        discovered_library_key="7",
    )
    session.add(row)
    session.commit()

    unlink_library(session, row)
    session.commit()

    reloaded = session.get(RefinerLibraryRow, row.id)
    assert reloaded is not None
    assert reloaded.name == "Films"
    assert reloaded.watched_folder == str(tmp_path)
    assert reloaded.discovered_from_connection_id is None
    assert reloaded.discovered_library_key is None


def test_a_connection_with_no_saved_key_cannot_be_asked(session: Session, tmp_path: Path) -> None:
    row = MediaManagerConnectionRow(kind="deluno", name="Half", enabled=True, base_url="http://h")
    session.add(row)
    session.commit()

    with pytest.raises(RefinerDiscoveryError) as exc:
        discoverable_libraries(session, MediaMopSettings.load(), row)
    assert "address and API key" in str(exc.value)
