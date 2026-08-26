"""Security guardrails for the media manager HTTP client."""

from __future__ import annotations

import pytest

from mediamop.platform.media_managers.manager_http import MediaManagerHttpClient, MediaManagerHttpError


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
