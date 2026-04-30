from __future__ import annotations

from fastapi.testclient import TestClient

from mediamop.api.factory import create_app


def test_non_essential_startup_failure_does_not_abort_startup(monkeypatch) -> None:
    def _boom(*_args, **_kwargs) -> None:
        raise RuntimeError("boom")

    monkeypatch.setattr("mediamop.core.lifespan.prune_logs_for_retention", _boom)

    with TestClient(create_app()) as client:
        response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
