from __future__ import annotations

import io
import urllib.error
from urllib.parse import parse_qs, urlparse

from mediamop.modules.pruner import pruner_http
from mediamop.modules.pruner.pruner_constants import MEDIA_SCOPE_MOVIES
from mediamop.modules.pruner.pruner_media_library import list_missing_primary_candidates


def _http_error(status: int, body: bytes) -> urllib.error.HTTPError:
    return urllib.error.HTTPError("http://server.test/Items", status, "Nope", hdrs=None, fp=io.BytesIO(body))


def test_http_get_json_returns_non_2xx_status_and_body(monkeypatch) -> None:
    def fake_urlopen(*args, **kwargs):  # noqa: ANN001, ARG001
        raise _http_error(401, b'{"message":"bad token"}')

    monkeypatch.setattr(pruner_http.urllib.request, "urlopen", fake_urlopen)

    status, body = pruner_http.http_get_json("http://server.test/Items")

    assert status == 401
    assert body == {"message": "bad token"}


def test_http_get_text_returns_non_2xx_status_and_body(monkeypatch) -> None:
    def fake_urlopen(*args, **kwargs):  # noqa: ANN001, ARG001
        raise _http_error(403, b"forbidden")

    monkeypatch.setattr(pruner_http.urllib.request, "urlopen", fake_urlopen)

    status, body = pruner_http.http_get_text("http://server.test/identity")

    assert status == 403
    assert body == "forbidden"


def test_jellyfin_missing_primary_fallback_still_handles_unsupported_filter(monkeypatch) -> None:
    calls: list[str] = []

    def fake_get_json(url: str, *, headers: dict[str, str] | None = None):  # noqa: ARG001
        calls.append(url)
        if "HasPrimaryImage=false" in url:
            return 400, {"error": "unsupported filter"}
        start_index = int(parse_qs(urlparse(url).query).get("StartIndex", ["0"])[0])
        if start_index > 0:
            return 200, {"Items": [], "TotalRecordCount": 2}
        return (
            200,
            {
                "Items": [
                    {"Id": "keep", "Name": "Needs art", "ImageTags": {}},
                    {"Id": "skip", "Name": "Has art", "ImageTags": {"Primary": "tag"}},
                ],
                "TotalRecordCount": 2,
            },
        )

    monkeypatch.setattr("mediamop.modules.pruner.pruner_media_library.http_get_json", fake_get_json)

    candidates, truncated = list_missing_primary_candidates(
        base_url="http://server.test",
        api_key="secret",
        media_scope=MEDIA_SCOPE_MOVIES,
        max_items=10,
    )

    assert [c["item_id"] for c in candidates] == ["keep"]
    assert truncated is False
    assert any("HasPrimaryImage=false" in call for call in calls)
    assert any("HasPrimaryImage=false" not in call for call in calls)
