"""OpenSubtitles client helpers — rate limit and login parsing."""

from __future__ import annotations

import io
from unittest.mock import patch

import httpx
import pytest

import mediamop.modules.subber.subber_opensubtitles_client as osc
from mediamop.modules.subber.subber_opensubtitles_client import SubberRateLimitError, _request


def test_login_extracts_token_from_top_level() -> None:
    with patch.object(osc, "_request", return_value=(200, {"token": "abc"})):
        assert osc.login("u", "p", "k") == "abc"


def test_request_429_raises_subber_rate_limit_error() -> None:
    request = httpx.Request("GET", "https://api.opensubtitles.com/api/v1/x")
    response = httpx.Response(429, request=request, content=io.BytesIO().getvalue())
    err = httpx.HTTPStatusError("Too Many Requests", request=request, response=response)
    with patch("mediamop.modules.subber.subber_opensubtitles_client.request_json", side_effect=err):
        with pytest.raises(SubberRateLimitError):
            _request("GET", "/subtitles?query=x", api_key="key", token=None)
