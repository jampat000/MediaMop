"""Unit tests for Fetcher healthz probe (no network in the failure path)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from mediamop.modules.fetcher.probe import probe_fetcher_healthz


@patch("mediamop.modules.fetcher.probe.urlopen")
def test_probe_fetcher_healthz_parses_json(mock_urlopen: MagicMock) -> None:
    mock_resp = MagicMock()
    mock_resp.status = 200
    mock_resp.read.return_value = b'{"status":"ok","app":"Fetcher","version":"1.2.3-test"}'
    mock_ctx = MagicMock()
    mock_ctx.__enter__.return_value = mock_resp
    mock_ctx.__exit__.return_value = None
    mock_urlopen.return_value = mock_ctx

    out = probe_fetcher_healthz("http://127.0.0.1:8000", timeout_sec=1.0)

    assert out.reachable is True
    assert out.http_status == 200
    assert out.fetcher_app == "Fetcher"
    assert out.fetcher_version == "1.2.3-test"
    assert out.latency_ms is not None
    called = mock_urlopen.call_args[0][0]
    assert called.full_url == "http://127.0.0.1:8000/healthz"


def test_probe_connection_refused() -> None:
    out = probe_fetcher_healthz("http://127.0.0.1:1", timeout_sec=1.0)
    assert out.reachable is False
    assert out.error_summary is not None
