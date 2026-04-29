"""Subber provider clients share one HTTP helper layer."""

from __future__ import annotations

from pathlib import Path


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
