"""Generic Torznab (RSS) client for arbitrary Torznab indexers."""

from __future__ import annotations

import logging
import urllib.parse
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from xml.etree import ElementTree

import httpx

from mediamop.modules.broker.broker_client_base import BROKER_CLIENT_HTTP_TIMEOUT, BrokerClientBase
from mediamop.modules.broker.broker_result import BrokerResult

logger = logging.getLogger(__name__)

TORZNAB_NS = "http://torznab.com/schemas/2010/feed"


def _tor_attr(item: ElementTree.Element, name: str) -> str:
    for el in item:
        if el.tag == f"{{{TORZNAB_NS}}}attr" and (el.get("name") or "").lower() == name.lower():
            return str(el.get("value") or "").strip()
        if el.tag.endswith("}" + name) or el.tag.endswith(name):
            if (el.text or "").strip():
                return (el.text or "").strip()
    return ""


class BrokerTorznabClient(BrokerClientBase):
    """Per-indexer Torznab instance (``kind == \"torznab\"``)."""

    protocol = "torrent"
    display_name = "Torznab"
    requires_api_key = False
    default_categories = [8000]

    def __init__(self, base_url: str, api_key: str = "", slug: str = "torznab") -> None:
        self._base = (base_url or "").strip().rstrip("/")
        self._key = api_key or ""
        self._slug = slug or "torznab"

    @property
    def slug(self) -> str:
        return self._slug

    async def search(
        self,
        query: str,
        categories: list[int],
        limit: int = 50,
        api_key: str = "",
        base_url: str = "",
    ) -> list[BrokerResult]:
        base = (base_url or self._base or "").strip().rstrip("/")
        if not base:
            return []
        key = urllib.parse.quote(api_key or self._key or "")
        q = urllib.parse.quote(query.strip() or "", safe="")
        cat = ",".join(str(c) for c in categories) if categories else ""
        cat_q = f"&cat={urllib.parse.quote(cat, safe=',')}" if cat else ""
        url = f"{base}/api?apikey={key}&t=search&q={q}&limit={max(1, min(100, limit))}{cat_q}"
        try:
            async with httpx.AsyncClient(timeout=BROKER_CLIENT_HTTP_TIMEOUT) as client:
                r = await client.get(url, headers={"User-Agent": "MediaMop-Broker/1.0"})
                if r.status_code != 200:
                    return []
                raw = r.content
        except Exception:
            logger.debug("Torznab search failed", exc_info=True)
            return []
        try:
            root = ElementTree.fromstring(raw)
        except ElementTree.ParseError:
            return []
        ch = root.find("channel")
        if ch is None:
            return []
        out: list[BrokerResult] = []
        for item in ch.findall("item"):
            title_el = item.find("title")
            link_el = item.find("link")
            pub_el = item.find("pubDate")
            title = (title_el.text or "").strip() if title_el is not None and title_el.text else ""
            link = (link_el.text or "").strip() if link_el is not None and link_el.text else ""
            if not title or not link:
                continue
            try:
                size = int(_tor_attr(item, "size") or "0")
            except ValueError:
                size = 0
            try:
                seeds = int(_tor_attr(item, "seeders") or "0")
            except ValueError:
                seeds = 0
            try:
                leech = int(_tor_attr(item, "leechers") or "0")
            except ValueError:
                leech = 0
            ih = (_tor_attr(item, "infohash") or _tor_attr(item, "info_hash") or "").strip().lower() or None
            pub: datetime | None = None
            if pub_el is not None and pub_el.text:
                try:
                    pub = parsedate_to_datetime(pub_el.text.strip())
                    if pub.tzinfo is None:
                        pub = pub.replace(tzinfo=timezone.utc)
                except (TypeError, ValueError, OverflowError):
                    pub = None
            out.append(
                BrokerResult(
                    title=title,
                    url=link,
                    magnet=link if link.startswith("magnet:") else None,
                    size=size,
                    seeders=seeds,
                    leechers=leech,
                    protocol="torrent",
                    indexer_slug=self._slug,
                    categories=categories or [8000],
                    published_at=pub,
                    imdb_id=None,
                    info_hash=ih,
                ),
            )
            if len(out) >= limit:
                break
        return out

    async def test(self, api_key: str = "", base_url: str = "") -> bool:
        base = (base_url or self._base or "").strip().rstrip("/")
        if not base:
            return False
        key = urllib.parse.quote(api_key or self._key or "")
        url = f"{base}/api?t=caps&apikey={key}"
        try:
            async with httpx.AsyncClient(timeout=BROKER_CLIENT_HTTP_TIMEOUT) as client:
                r = await client.get(url, headers={"User-Agent": "MediaMop-Broker/1.0"})
                return r.status_code == 200
        except Exception:
            return False
