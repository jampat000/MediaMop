"""SubDL subtitle client — REST API v1 with free API key."""

from __future__ import annotations

import logging
import urllib.parse
from typing import Any

from mediamop.modules.subber.subber_http_client import DEFAULT_USER_AGENT, request_bytes, request_json

BASE = "https://api.subdl.com/api/v1"
DOWNLOAD_BASE = "https://dl.subdl.com"
USER_AGENT = DEFAULT_USER_AGENT
logger = logging.getLogger(__name__)


def _get(path: str) -> dict[str, Any] | None:
    url = f"{BASE}{path}"
    try:
        _code, parsed = request_json(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"}, timeout=30)
        return parsed if isinstance(parsed, dict) else None
    except Exception:
        logger.exception("SubDL request failed.")
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
    """Search SubDL. Returns list of subtitle dicts with download_url."""
    params = [
        f"api_key={urllib.parse.quote(api_key.strip())}",
        f"film_name={urllib.parse.quote(query.strip())}",
        f"type={'tv' if media_scope == 'tv' else 'movie'}",
    ]
    if languages:
        params.append(f"languages={urllib.parse.quote(','.join(l.upper() for l in languages))}")
    if media_scope == "tv" and season_number is not None:
        params.append(f"season_number={int(season_number)}")
    if media_scope == "tv" and episode_number is not None:
        params.append(f"episode_number={int(episode_number)}")
    params.append("subs_per_page=5")
    body = _get("/subtitles?" + "&".join(params))
    if not isinstance(body, dict) or not body.get("status"):
        return []
    subs = body.get("subtitles") or []
    if not isinstance(subs, list):
        return []
    out = []
    for s in subs:
        if not isinstance(s, dict):
            continue
        url = s.get("url") or s.get("download_link") or ""
        lang = str(s.get("lang") or s.get("language") or "").lower()[:10]
        if url:
            full_url = url if url.startswith("http") else f"{DOWNLOAD_BASE}{url}"
            out.append({"download_url": full_url, "language": lang, "hearing_impaired": bool(s.get("hi"))})
    return out


def download(*, download_url: str) -> bytes:
    """Download subtitle zip/srt from SubDL."""
    _code, data = request_bytes(download_url, headers={"User-Agent": USER_AGENT}, timeout=60)
    return data
