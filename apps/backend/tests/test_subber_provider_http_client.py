"""Subber provider clients share one HTTP helper layer."""

from __future__ import annotations

from pathlib import Path

import io
import urllib.error

from mediamop.modules.subber import subber_http_client


def test_subber_provider_clients_do_not_open_urls_directly() -> None:
    root = Path(__file__).resolve().parents[1] / "src" / "mediamop" / "modules" / "subber"
    provider_files = [
        path
        for path in root.glob("subber_*_client.py")
        if path.name not in {"subber_http_client.py", "subber_arr_client.py"}
    ]

    assert provider_files
    for path in provider_files:
        text = path.read_text(encoding="utf-8")
        assert "urllib.request.urlopen" not in text, path.name
        assert "urllib.request.Request" not in text, path.name


def test_subber_request_json_treats_malformed_json_as_empty_payload(monkeypatch) -> None:
    monkeypatch.setattr(subber_http_client, "request_text", lambda *a, **k: (200, "{not-json"))

    assert subber_http_client.request_json("https://example.invalid") == (200, None)


def test_subber_http_error_json_preserves_malformed_payload() -> None:
    exc = urllib.error.HTTPError(
        "https://example.invalid",
        500,
        "bad",
        {},
        fp=io.BytesIO(b"{not-json"),
    )

    assert subber_http_client.decode_http_error_json(exc) == {"raw": "{not-json"}
