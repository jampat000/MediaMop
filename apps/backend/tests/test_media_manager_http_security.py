"""Security guardrails for the media manager HTTP client."""

from __future__ import annotations

import email
import io
import urllib.error
import urllib.request

import pytest

from mediamop.platform.media_managers.manager_http import (
    MediaManagerHttpClient,
    MediaManagerHttpError,
    MediaManagerRateLimitedError,
)


@pytest.mark.parametrize(
    "base_url",
    [
        "ftp://127.0.0.1:8989",
        "http://user:pass@127.0.0.1:8989",
        "http://127.0.0.1:8989/?x=1",
        "http://127.0.0.1:8989/#fragment",
    ],
)
def test_manager_client_rejects_unsafe_base_urls(base_url: str) -> None:
    with pytest.raises(MediaManagerHttpError):
        MediaManagerHttpClient(base_url, "api-key")


def test_manager_client_rejects_absolute_api_paths() -> None:
    client = MediaManagerHttpClient("http://127.0.0.1:8989", "api-key")

    with pytest.raises(MediaManagerHttpError):
        client.get_json("http://169.254.169.254/latest/meta-data/")


def test_rate_limit_response_is_distinguishable_and_carries_the_backoff(monkeypatch: pytest.MonkeyPatch) -> None:
    """429 must not read like any other failure — the caller has to back off, not retry."""

    client = MediaManagerHttpClient("http://127.0.0.1:8989", "api-key")

    def _raise(_req, timeout=None):
        raise urllib.error.HTTPError(
            "http://127.0.0.1:8989/api/v3/queue",
            429,
            "Too Many Requests",
            email.message_from_string("Retry-After: 42"),
            io.BytesIO(b"slow down"),
        )

    monkeypatch.setattr(urllib.request, "urlopen", _raise)
    with pytest.raises(MediaManagerRateLimitedError) as excinfo:
        client.get_json("/api/v3/queue")
    assert excinfo.value.retry_after_seconds == 42.0


def test_a_retry_after_date_is_accepted_without_inventing_a_delay(monkeypatch: pytest.MonkeyPatch) -> None:
    client = MediaManagerHttpClient("http://127.0.0.1:8989", "api-key")

    def _raise(_req, timeout=None):
        raise urllib.error.HTTPError(
            "http://127.0.0.1:8989/api/v3/queue",
            429,
            "Too Many Requests",
            email.message_from_string("Retry-After: Wed, 21 Oct 2026 07:28:00 GMT"),
            io.BytesIO(b""),
        )

    monkeypatch.setattr(urllib.request, "urlopen", _raise)
    with pytest.raises(MediaManagerRateLimitedError) as excinfo:
        client.get_json("/api/v3/queue")
    assert excinfo.value.retry_after_seconds is None


def test_a_queue_delete_sends_booleans_the_way_arr_binds_them(monkeypatch: pytest.MonkeyPatch) -> None:
    """ASP.NET binds "true"/"false"; "1" would be a 400 and the reject would silently fall back."""

    client = MediaManagerHttpClient("http://127.0.0.1:8989", "api-key")
    seen: list[urllib.request.Request] = []

    class _Response(io.BytesIO):
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    def _open(req, timeout=None):
        seen.append(req)
        return _Response(b"")

    monkeypatch.setattr(urllib.request, "urlopen", _open)
    client.delete("/api/v3/queue/17", params={"removeFromClient": True, "blocklist": True})
    (req,) = seen
    assert req.get_method() == "DELETE"
    assert req.full_url == "http://127.0.0.1:8989/api/v3/queue/17?removeFromClient=true&blocklist=true"
    assert req.get_header("X-api-key") == "api-key"


def test_a_refused_queue_delete_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    client = MediaManagerHttpClient("http://127.0.0.1:8989", "api-key")

    def _raise(_req, timeout=None):
        raise urllib.error.HTTPError(
            "http://127.0.0.1:8989/api/v3/queue/17", 404, "Not Found", email.message_from_string(""), io.BytesIO(b"")
        )

    monkeypatch.setattr(urllib.request, "urlopen", _raise)
    with pytest.raises(MediaManagerHttpError):
        client.delete("/api/v3/queue/17")


def test_the_queue_dialect_removes_and_blocklists_one_item(monkeypatch: pytest.MonkeyPatch) -> None:
    """Sonarr/Radarr openapi.json: DELETE /api/v3/queue/{id}, removeFromClient + blocklist, skipRedownload left false."""

    from mediamop.platform.media_managers.manager_dialects import port_for_kind
    from mediamop.platform.media_managers.manager_port import ManagerConnection

    calls: list[tuple[str, dict | None]] = []
    monkeypatch.setattr(MediaManagerHttpClient, "delete", lambda self, path, params=None: calls.append((path, params)))
    port = port_for_kind("sonarr")
    assert port is not None and port.capabilities().removes_queue_items is True
    connection = ManagerConnection(kind="sonarr", name="Sonarr", base_url="http://127.0.0.1:8989", api_key="k")
    port.remove_queue_item(connection, {"id": 99, "downloadId": "x"})
    assert calls == [("/api/v3/queue/99", {"removeFromClient": True, "blocklist": True})]

    with pytest.raises(MediaManagerHttpError):
        port.remove_queue_item(connection, {"downloadId": "no id"})


def test_a_handoff_manager_does_not_remove_queue_items() -> None:
    from mediamop.platform.media_managers.manager_dialects import port_for_kind
    from mediamop.platform.media_managers.manager_port import ManagerConnection

    port = port_for_kind("deluno")
    assert port is not None and port.capabilities().removes_queue_items is False
    with pytest.raises(MediaManagerHttpError):
        port.remove_queue_item(
            ManagerConnection(kind="deluno", name="Deluno", base_url="http://127.0.0.1:5099", api_key="k"), {"id": 1}
        )
