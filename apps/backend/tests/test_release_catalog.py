from __future__ import annotations

import pytest

from mediamop.platform.suite_settings import release_catalog


def test_normalize_release_version_strips_v_prefix() -> None:
    assert release_catalog.normalize_release_version("v2.0.8") == "2.0.8"
    assert release_catalog.normalize_release_version("2.0.8") == "2.0.8"
    assert release_catalog.tag_for_version("2.0.8") == "v2.0.8"


def test_fetch_release_record_by_version_rejects_wrong_returned_tag(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = {
        "tag_name": "v2.0.7",
        "name": "MediaMop 2.0.7",
        "html_url": "https://github.com/jampat000/MediaMop/releases/tag/v2.0.7",
        "published_at": "2026-05-07T00:00:00Z",
        "draft": False,
        "prerelease": False,
        "assets": [],
    }

    class _Response:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, object]:
            return payload

    class _Client:
        def __enter__(self) -> "_Client":
            return self

        def __exit__(self, exc_type, exc, tb) -> None:
            return None

        def get(self, url: str) -> _Response:
            return _Response()

    monkeypatch.setattr(release_catalog.httpx, "Client", lambda **_kwargs: _Client())

    with pytest.raises(ValueError, match="Release tag mismatch"):
        release_catalog.fetch_release_record_by_version(
            "2.0.8",
            user_agent_version="2.0.7",
        )


def test_fetch_release_record_by_version_rejects_prerelease(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = {
        "tag_name": "v2.0.8",
        "name": "MediaMop 2.0.8-rc1",
        "html_url": "https://github.com/jampat000/MediaMop/releases/tag/v2.0.8",
        "published_at": "2026-05-07T00:00:00Z",
        "draft": False,
        "prerelease": True,
        "assets": [],
    }

    class _Response:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, object]:
            return payload

    class _Client:
        def __enter__(self) -> "_Client":
            return self

        def __exit__(self, exc_type, exc, tb) -> None:
            return None

        def get(self, url: str) -> _Response:
            return _Response()

    monkeypatch.setattr(release_catalog.httpx, "Client", lambda **_kwargs: _Client())

    with pytest.raises(ValueError, match="not a stable published release"):
        release_catalog.fetch_release_record_by_version(
            "2.0.8",
            user_agent_version="2.0.7",
        )
