"""Contract port of the retired Python backend's tests/test_bootstrap_status_router.py.

The original injects database errors into ``bootstrap_allowed``. Black-box, the one failure a
running server can be put into is a database whose ``users`` table is missing.
"""

from __future__ import annotations

from tests.contract.support import seed
from tests.contract.support.client import API


def test_bootstrap_status_missing_table_returns_503(server_factory, client_factory) -> None:
    """Guest-first probe: never HTTP 500; a missing schema is a 503 that says so."""

    sut = server_factory()
    with seed.stopped(sut) as conn:
        conn.execute("PRAGMA foreign_keys=OFF")
        conn.execute("DROP TABLE users")

    r = client_factory(sut).get(f"{API}/auth/bootstrap/status")
    assert r.status_code == 503, r.text
    detail = r.json().get("detail")
    assert isinstance(detail, str) and len(detail) > 10
    assert "schema" in detail.lower()
