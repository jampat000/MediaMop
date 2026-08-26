"""HEAD should answer like GET, without a body.

FastAPI registers only the declared method, so `@router.get(...)` used to leave HEAD
falling through to a 404 — `HEAD /health` said the endpoint did not exist while
`GET /health` returned 200. Anything probing with HEAD before committing to a real
request was told the wrong thing.
"""

from __future__ import annotations

from starlette.testclient import TestClient


def test_head_on_a_get_route_answers_like_get(client_with_admin: TestClient) -> None:
    get = client_with_admin.get("/health")
    head = client_with_admin.head("/health")

    assert get.status_code == 200
    assert head.status_code == 200
    assert head.content == b""


def test_head_carries_the_same_content_type_as_get(client_with_admin: TestClient) -> None:
    get = client_with_admin.get("/health")
    head = client_with_admin.head("/health")

    assert head.headers.get("content-type") == get.headers.get("content-type")


def test_head_on_the_readiness_probe_answers(client_with_admin: TestClient) -> None:
    head = client_with_admin.head("/ready")
    assert head.status_code in (200, 503)
    assert head.content == b""


def test_head_on_a_post_only_route_says_method_not_allowed(client_with_admin: TestClient) -> None:
    """A POST-only webhook has nothing for HEAD to describe.

    Routing it as a GET gets the spec-correct answer for a path that exists but has no
    GET handler: 405, not the 404 FastAPI produced before. That matters because callers
    probe webhooks with HEAD, and 404 tells them the endpoint is missing when it is not.
    """

    head = client_with_admin.head("/api/v1/intake/webhook/deluno")
    assert head.status_code == 405


def test_head_on_a_path_that_does_not_exist_is_not_found(client_with_admin: TestClient) -> None:
    assert client_with_admin.head("/api/v1/nothing-here").status_code == 404


def test_get_still_returns_a_body(client_with_admin: TestClient) -> None:
    """The middleware must not strip bodies from ordinary requests."""

    r = client_with_admin.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"
