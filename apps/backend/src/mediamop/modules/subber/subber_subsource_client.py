"""SubSource subtitle client — REST API with X-API-Key header."""

from __future__ import annotations

import logging
import urllib.parse
from typing import Any

from mediamop.modules.subber.subber_http_client import DEFAULT_USER_AGENT, request_bytes, request_json

BASE = "https://api.subsource.net"
USER_AGENT = DEFAULT_USER_AGENT
logger = logging.getLogger(__name__)


def _request(path: str, *, api_key: str, method: str = "GET", body: dict | None = None) -> dict[str, Any] | list | None:
    url = f"{BASE}{path}"
    headers: dict[str, str] = {
        "User-Agent": USER_AGENT,
        "Accept": "application/json",
        "X-API-Key": api_key.strip(),
    }
    try:
        _code, parsed = request_json(url, method=method, headers=headers, body=body, timeout=30)
        return parsed
    except Exception:
        logger.exception("SubSource request failed: %s", url)
        return None


def search(
    *,
    api_key: str,
    query: str,
    season_number: int | None,
    episode_number: int | None,
    languages: list[str],
    media_scope: str,
) -> list[dict[str, Any]]:
    """Search SubSource. Returns list of subtitle dicts."""
    params = [f"query={urllib.parse.quote(query.strip())}"]
    if media_scope == "tv":
        params.append("type=tv")
        if season_number is not None:
            params.append(f"season={int(season_number)}")
        if episode_number is not None:
            params.append(f"episode={int(episode_number)}")
    else:
        params.append("type=movie")
    if languages:
        params.append(f"langs={urllib.parse.quote(','.join(languages))}")
    result = _request("/api/v1/subtitles?" + "&".join(params), api_key=api_key)
    if not isinstance(result, dict):
        return []
    subs = result.get("subtitles") or result.get("data") or result.get("results") or []
    if not isinstance(subs, list):
        return []
    out = []
    for s in subs:
        if not isinstance(s, dict):
            continue
        dl = s.get("download_url") or s.get("url") or s.get("downloadLink") or ""
        lang = str(s.get("lang") or s.get("language") or "").lower()[:10]
        if dl:
            out.append({"download_url": str(dl), "language": lang, "hearing_impaired": bool(s.get("hi") or s.get("hearing_impaired"))})
    return out


def download(*, download_url: str, api_key: str) -> bytes:
    """Download subtitle from SubSource."""
    _code, data = request_bytes(download_url, headers={"User-Agent": USER_AGENT, "X-API-Key": api_key.strip()}, timeout=60)
    return data
