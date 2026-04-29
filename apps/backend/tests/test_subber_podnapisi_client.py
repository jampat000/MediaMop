"""Unit tests for Podnapisi client (network mocked)."""

from __future__ import annotations

from unittest.mock import patch

from mediamop.modules.subber import subber_podnapisi_client as pnc


@patch("mediamop.modules.subber.subber_podnapisi_client.request_json")
def test_podnapisi_search_parses_data_list(mock_request_json) -> None:
    body = {"data": [{"id": "42", "language": "en", "flags": []}]}
    mock_request_json.return_value = (200, body)
    items = pnc.search(
        query="Test Show",
        season_number=1,
        episode_number=2,
        languages=["en"],
        media_scope="tv",
    )
    assert len(items) == 1
    assert items[0]["id"] == "42"
