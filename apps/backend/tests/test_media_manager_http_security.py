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
