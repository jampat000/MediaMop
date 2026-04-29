"""Subf2m subtitle client — web scraper (fragile; may break if site changes).

NOTE: Subf2m does not have a public API. This client scrapes HTML.
It may stop working without notice if Subf2m changes their markup.
"""

from __future__ import annotations

import logging
import re
import urllib.parse
from typing import Any

from mediamop.modules.subber.subber_http_client import HTML_USER_AGENT, request_bytes, request_text

BASE = "https://subf2m.co"
USER_AGENT = HTML_USER_AGENT
logger = logging.getLogger(__name__)


def _get_html(url: str) -> str:
    try:
        _code, text = request_text(url, headers={"User-Agent": USER_AGENT, "Accept": "text/html"}, timeout=30)
        return text
    except Exception:
        logger.exception("Subf2m request failed: %s", url)
        return ""


def search(
    *,
    query: str,
    season_number: int | None,
    episode_number: int | None,
    languages: list[str],
    media_scope: str,
) -> list[dict[str, Any]]:
    """Search Subf2m. Returns list of dicts with download_page_url."""
    encoded = urllib.parse.quote(query.strip().replace(" ", "-"))
    url = f"{BASE}/subtitles/searchbytitle?query={encoded}&l="
    html = _get_html(url)
    if not html:
        return []
    # Extract first result link
    matches = re.findall(r'href="(/subtitles/[^"]+)"', html)
    if not matches:
        return []
    sub_page = BASE + matches[0]
    sub_html = _get_html(sub_page)
    if not sub_html:
        return []
    # Find download links
    dl_matches = re.findall(r'href="(/subtitle/[^"]+\.zip[^"]*)"', sub_html)
    if not dl_matches:
        dl_matches = re.findall(r'href="(/subtitle/[^"]+)"', sub_html)
    lang = (languages[0] if languages else "en").lower()[:10]
    out = []
    for dl in dl_matches[:3]:
        out.append({"download_url": BASE + dl, "language": lang, "hearing_impaired": False})
    return out


def download(*, download_url: str) -> bytes:
    """Download subtitle from Subf2m."""
    _code, data = request_bytes(download_url, headers={"User-Agent": USER_AGENT}, timeout=60)
    return data
