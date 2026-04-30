"""Subber provider clients share one HTTP helper layer."""

from __future__ import annotations

from pathlib import Path

import httpx

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
    request = httpx.Request("GET", "https://example.invalid")
    response = httpx.Response(
        500,
        request=request,
        content=b"{not-json",
    )
    exc = httpx.HTTPStatusError("bad", request=request, response=response)

    assert subber_http_client.decode_http_error_json(exc) == {"raw": "{not-json"}


def test_safe_provider_url_blocks_local_targets() -> None:
    for url in (
        "http://localhost/file.srt",
        "http://127.0.0.1/file.srt",
        "http://169.254.1.1/file.srt",
        "http://10.0.0.5/file.srt",
    ):
        try:
            subber_http_client.safe_provider_url(url)
        except ValueError as exc:
            assert "Blocked provider URL host" in str(exc)
        else:
            raise AssertionError(f"expected blocked URL for {url}")


def test_safe_provider_url_allows_public_https_targets() -> None:
    assert subber_http_client.safe_provider_url("https://subtitles.example/file.srt") == "https://subtitles.example/file.srt"
