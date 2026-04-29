"""YifySubtitles client — movies only.

NOTE: YifySubtitles does not have a public stable API.
This client uses their unofficial JSON endpoint which may change.
"""

from __future__ import annotations

import logging
import urllib.parse
from typing import Any

from mediamop.modules.subber.subber_http_client import DEFAULT_USER_AGENT, request_bytes, request_json

BASE = "https://yifysubtitles.ch"
USER_AGENT = DEFAULT_USER_AGENT
logger = logging.getLogger(__name__)


def _get(url: str) -> dict[str, Any] | list | None:
    try:
        _code, parsed = request_json(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"}, timeout=30)
        return parsed
    except Exception:
        logger.exception("YifySubtitles request failed: %s", url)
        return None


def search(
    *,
    query: str,
    languages: list[str],
) -> list[dict[str, Any]]:
    """Search YifySubtitles for movie subtitles."""
    encoded = urllib.parse.quote(query.strip())
    result = _get(f"{BASE}/api?q={encoded}")
    if not isinstance(result, dict):
        return []
    subs = result.get("subs") or result.get("subtitles") or result.get("data") or []
    if not isinstance(subs, list):
        return []
    pref_langs = {l.lower()[:2] for l in languages} if languages else {"en"}
    out = []
    for s in subs:
        if not isinstance(s, dict):
            continue
        lang = str(s.get("lang") or s.get("language") or "").lower()[:10]
        if lang[:2] not in pref_langs and pref_langs:
            continue
        dl = s.get("url") or s.get("download") or s.get("link") or ""
        if dl:
            full = dl if dl.startswith("http") else f"{BASE}{dl}"
            out.append({"download_url": full, "language": lang, "hearing_impaired": bool(s.get("hi"))})
    return out


def download(*, download_url: str) -> bytes:
    """Download subtitle from YifySubtitles."""
    _code, data = request_bytes(download_url, headers={"User-Agent": USER_AGENT}, timeout=60)
    return data
