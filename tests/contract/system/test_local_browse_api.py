"""Port of apps/backend/tests/test_local_browse_api.py (GET ``/api/v1/system/directories``)."""

from __future__ import annotations

import tempfile
import uuid
from pathlib import Path

import pytest

from tests.contract.support.client import API
from tests.contract.system import _helpers as h

DIRECTORIES = f"{API}/system/directories"


@pytest.fixture(scope="module", autouse=True)
def _users(server) -> None:
    h.seed_users(server)


def test_system_directories_requires_operator(server, client_factory) -> None:
    viewer = h.signed_in_viewer(server, client_factory)

    r = viewer.get(DIRECTORIES)

    assert r.status_code == 403


def test_system_directories_lists_roots(admin) -> None:
    r = admin.get(DIRECTORIES)

    assert r.status_code == 200, r.text
    body = r.json()
    assert body["current_path"] is None
    assert body["parent_path"] is None
    assert isinstance(body["entries"], list)
    assert body["entries"]
    assert {"name", "path", "kind", "description"}.issubset(body["entries"][0])


def test_system_directories_returns_not_found(admin) -> None:
    # The server runs on this machine, so a folder missing under this temp directory is missing for it too.
    missing_path = Path(tempfile.gettempdir()) / f"weir-missing-{uuid.uuid4()}"

    r = admin.get(DIRECTORIES, params={"path": str(missing_path)})

    assert r.status_code == 404
    assert r.json()["detail"] == "The requested directory does not exist."
