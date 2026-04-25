"""Security guardrails for the Sonarr/Radarr v3 HTTP client."""

from __future__ import annotations

import pytest

from mediamop.platform.arr_library.arr_v3_http import ArrLibraryV3Client, ArrLibraryV3HttpError


@pytest.mark.parametrize(
    "base_url",
    [
        "ftp://127.0.0.1:8989",
        "http://user:pass@127.0.0.1:8989",
        "http://127.0.0.1:8989/?x=1",
        "http://127.0.0.1:8989/#fragment",
    ],
)
def test_arr_v3_client_rejects_unsafe_base_urls(base_url: str) -> None:
    with pytest.raises(ArrLibraryV3HttpError):
        ArrLibraryV3Client(base_url, "api-key")


def test_arr_v3_client_rejects_absolute_api_paths() -> None:
    client = ArrLibraryV3Client("http://127.0.0.1:8989", "api-key")

    with pytest.raises(ArrLibraryV3HttpError):
        client.get_json("http://169.254.169.254/latest/meta-data/")
