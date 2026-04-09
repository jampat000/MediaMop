"""Database session dependency (Phase 4)."""

from __future__ import annotations

from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from mediamop.api.deps import get_db_session


def test_get_db_session_503_without_factory() -> None:
    """Mini-app without lifespan wiring must not crash — returns service unavailable."""
    app = FastAPI()

    @app.get("/needs-db")
    def needs_db(_session: Session = Depends(get_db_session)) -> dict[str, str]:
        return {"ok": "yes"}

    client = TestClient(app)
    response = client.get("/needs-db")
    assert response.status_code == 503
    assert "Database not configured" in response.json().get("detail", "")
