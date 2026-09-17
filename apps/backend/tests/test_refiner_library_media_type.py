"""A library's ``media_type`` (formerly ``media_scope``) and the retirement of the scope-shaped routes (#460).

The rename is the least of it. What matters is that nothing an operator saved is lost on the way
(the migration renames in place rather than rebuilding a table whose children cascade), that a
backup taken before the rename still restores, that the folder rules the retired path-settings
screen enforced now protect every library, and that a hand-off lands in the library whose watched
folder actually holds the file — so a second film library is a normal thing to have.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.config import Config
from sqlalchemy import select
from starlette.testclient import TestClient

from alembic import command
from tests.integration_helpers import auth_post, auth_put
from tests.integration_helpers import csrf as fetch_csrf
from weir.core.config import WeirSettings
from weir.core.db import create_db_engine, create_session_factory
from weir.platform.configuration_bundle.service import _restore_refiner_libraries
from weir.refiner.jobs_model import RefinerJob
from weir.refiner.refiner_library_model import RefinerLibraryRow

# --- the migration --------------------------------------------------------------------------------


def _config(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Config:
    monkeypatch.setenv("WEIR_SESSION_SECRET", "pytest-session-secret-32-chars-min!!")
    home = tmp_path / "weirhome_media_type"
    home.mkdir()
    monkeypatch.setenv("WEIR_HOME", str(home))
    backend = Path(__file__).resolve().parents[1]
    monkeypatch.chdir(backend)
    return Config(str(backend / "alembic.ini"))


def _columns(engine: sa.Engine) -> set[str]:
    return {c["name"] for c in sa.inspect(engine).get_columns("refiner_libraries")}


def test_the_rename_keeps_every_library_and_everything_hanging_off_it(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A table rebuild would drop refiner_libraries, and its children cascade. This must not."""

    cfg = _config(monkeypatch, tmp_path)
    command.upgrade(cfg, "0032_media_manager_handoffs")
    engine = create_db_engine(WeirSettings.load())
    with engine.begin() as conn:
        if "media_scope" not in _columns(engine):
            # A greenfield 0001 builds today's models; put the old name back to model an upgrade.
            conn.execute(sa.text("ALTER TABLE refiner_libraries RENAME COLUMN media_type TO media_scope"))
    with engine.begin() as conn:
        library_id = conn.execute(sa.text("select id from refiner_libraries where media_scope = 'tv'")).scalar_one()
        conn.execute(
            sa.text("insert into refiner_files (library_id, relative_path) values (:id, 'Show/S01E01.mkv')"),
            {"id": library_id},
        )
    engine.dispose()

    command.upgrade(cfg, "head")

    engine = create_db_engine(WeirSettings.load())
    assert "media_type" in _columns(engine)
    assert "media_scope" not in _columns(engine)
    with engine.connect() as conn:
        assert (
            conn.execute(
                sa.text("select media_type from refiner_libraries where id = :id"), {"id": library_id}
            ).scalar_one()
            == "tv"
        )
        assert conn.execute(sa.text("select count(*) from refiner_files")).scalar_one() == 1


# --- backups ----------------------------------------------------------------------------------------


def test_a_backup_taken_before_the_rename_still_restores_its_media_type() -> None:
    factory = create_session_factory(create_db_engine(WeirSettings.load()))
    with factory() as session:
        _restore_refiner_libraries(
            session,
            {
                "refiner_rule_sets": [],
                "refiner_libraries": [{"id": 1, "name": "Shows", "media_scope": "tv"}],
            },
        )
        restored = session.scalars(select(RefinerLibraryRow)).all()
        assert [(row.name, row.media_type) for row in restored] == [("Shows", "tv")]
        session.rollback()


# --- the API ----------------------------------------------------------------------------------------


def _login(client: TestClient) -> TestClient:
    response = auth_post(
        client,
        "/api/v1/auth/login",
        json={"username": "alice", "password": "test-password-strong", "csrf_token": fetch_csrf(client)},
    )
    assert response.status_code == 200, response.text
    return client


def _create(client: TestClient, **overrides: object):
    body: dict[str, object] = {
        "csrf_token": fetch_csrf(client),
        "name": "Films 4K",
        "media_type": "movie",
        "watched_folder": "/srv/films4k/in",
        "output_folder": "/srv/films4k/out",
    }
    body.update(overrides)
    return auth_post(client, "/api/v1/refiner/libraries", json=body)


@pytest.fixture
def operator(client_with_admin: TestClient):
    client = _login(client_with_admin)
    yield client
    factory = create_session_factory(create_db_engine(WeirSettings.load()))
    with factory() as session:
        for row in session.scalars(select(RefinerLibraryRow)):
            if row.name not in ("Movies", "TV"):
                session.delete(row)
        session.execute(sa.delete(RefinerJob))
        session.commit()


def test_the_scope_shaped_routes_are_gone(operator: TestClient) -> None:
    for path in ("/api/v1/refiner/path-settings", "/api/v1/refiner/remux-rules-settings"):
        assert operator.get(path).status_code == 404, path


def test_a_library_reports_its_media_type(operator: TestClient) -> None:
    response = _create(operator)
    assert response.status_code == 201, response.text
    assert response.json()["media_type"] == "movie"
    assert "media_scope" not in response.json()


@pytest.mark.parametrize(
    ("overrides", "expected"),
    [
        ({"output_folder": "/srv/films4k/in/done"}, "watched folder and output folder overlap"),
        ({"work_folder": "/srv/films4k/in"}, "watched folder and work folder overlap"),
        ({"output_folder": ""}, "Set an output folder"),
    ],
)
def test_a_library_whose_own_folders_overlap_is_refused(
    operator: TestClient, overrides: dict[str, object], expected: str
) -> None:
    response = _create(operator, **overrides)
    assert response.status_code == 400, response.text
    assert expected in response.json()["detail"]


def test_a_library_cannot_share_another_librarys_folders(operator: TestClient) -> None:
    assert _create(operator).status_code == 201
    response = _create(
        operator, name="Films 1080p", watched_folder="/srv/films4k/in/1080p", output_folder="/srv/films1080/out"
    )
    assert response.status_code == 400, response.text
    assert "overlaps the watched folder of 'Films 4K'" in response.json()["detail"]


def test_a_second_film_library_is_normal(operator: TestClient) -> None:
    first = _create(operator)
    second = _create(
        operator, name="Films 1080p", watched_folder="/srv/films1080/in", output_folder="/srv/films1080/out"
    )
    assert first.status_code == 201, first.text
    assert second.status_code == 201, second.text
    edited = auth_put(
        operator,
        f"/api/v1/refiner/libraries/{second.json()['id']}",
        json={
            "csrf_token": fetch_csrf(operator),
            "name": "Films 1080p",
            "media_type": "movie",
            "watched_folder": "/srv/films1080/incoming",
            "output_folder": "/srv/films1080/out",
        },
    )
    assert edited.status_code == 200, edited.text


def test_a_hand_off_lands_in_the_library_whose_folder_holds_the_file(operator: TestClient) -> None:
    """Resolving by type alone always picked the first film library, whatever folder the file was in."""

    import json

    # Another test's connection may carry a webhook secret; this hand-off is about routing, not auth.
    from weir.platform.media_managers.connection_model import MediaManagerConnectionRow

    with create_session_factory(create_db_engine(WeirSettings.load()))() as session:
        session.execute(sa.delete(MediaManagerConnectionRow))
        session.commit()

    _create(operator)  # Films 4K: /srv/films4k/in
    second = _create(
        operator, name="Films 1080p", watched_folder="/srv/films1080/in", output_folder="/srv/films1080/out"
    )
    response = operator.post(
        "/api/v1/intake/webhook/deluno",
        json={
            "eventType": "deluno.processor-handoff",
            "handoffId": "h-1080",
            "mediaType": "movies",
            "sourcePath": "/srv/films1080/in/Heat.1995/heat.mkv",
        },
    )
    assert response.status_code == 200, response.text

    factory = create_session_factory(create_db_engine(WeirSettings.load()))
    with factory() as session:
        job = session.scalars(select(RefinerJob).where(RefinerJob.dedupe_key.like("%handoff:h-1080"))).one()
    payload = json.loads(job.payload_json or "{}")
    assert payload["library_id"] == second.json()["id"]
    assert payload["relative_media_path"] == "Heat.1995/heat.mkv"
    assert payload["media_scope"] == "movie"
