"""Contract port of the retired Python backend's tests/test_head_mirrors_get.py (HEAD answers like GET, without a body)."""

from __future__ import annotations

from tests.contract.support.client import WeirClient


def test_head_on_a_get_route_answers_like_get(client: WeirClient) -> None:
    get = client.get("/health")
    head = client.head("/health")

    assert get.status_code == 200
    assert head.status_code == 200
    assert head.content == b""


def test_head_carries_the_same_content_type_as_get(client: WeirClient) -> None:
    get = client.get("/health")
    head = client.head("/health")

    assert head.headers.get("content-type") == get.headers.get("content-type")


def test_head_on_the_readiness_probe_answers(client: WeirClient) -> None:
    head = client.head("/ready")
    assert head.status_code in (200, 503)
    assert head.content == b""


def test_head_on_a_post_only_route_says_method_not_allowed(server_factory, client_factory) -> None:
    """A POST-only webhook has nothing for HEAD to describe: 405, not 404.

    Like the original, this runs without a bundled web app. With ``WEIR_WEB_DIST`` set, the web
    app's catch-all mount answers GET and HEAD on this path with 404 instead.
    """

    sut = server_factory(env={"WEIR_WEB_DIST": ""})
    assert client_factory(sut).head("/api/v1/intake/webhook/deluno").status_code == 405


def test_head_on_a_path_that_does_not_exist_is_not_found(client: WeirClient) -> None:
    assert client.head("/api/v1/nothing-here").status_code == 404


def test_get_still_returns_a_body(client: WeirClient) -> None:
    """The middleware must not strip bodies from ordinary requests."""

    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"
