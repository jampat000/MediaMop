"""Shared Newznab JSON API helpers for Usenet indexer clients."""

from __future__ import annotations

import logging
import urllib.parse
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any

import httpx

from mediamop.modules.broker.broker_client_base import BROKER_CLIENT_HTTP_TIMEOUT, BrokerClientBase
from mediamop.modules.broker.broker_result import BrokerResult

logger = logging.getLogger(__name__)


def _parse_pub_date(raw: str) -> datetime | None:
    s = (raw or "").strip()
    if not s:
        return None
    try:
        dt = parsedate_to_datetime(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except (TypeError, ValueError, OverflowError):
        return None


def _items_from_newznab_json(data: Any) -> list[dict[str, Any]]:
    if not isinstance(data, dict):
        return []
    ch = data.get("channel")
    if isinstance(ch, dict):
        it = ch.get("item")
        if isinstance(it, list):
            return [x for x in it if isinstance(x, dict)]
        if isinstance(it, dict):
            return [it]
    it2 = data.get("item")
    if isinstance(it2, list):
        return [x for x in it2 if isinstance(x, dict)]
    if isinstance(it2, dict):
        return [it2]
    return []


def _attrs_list(item: dict[str, Any]) -> list[dict[str, Any]]:
    attrs = item.get("@attributes")
    if isinstance(attrs, dict):
        return [attrs]
    al = item.get("attr")
    if isinstance(al, list):
        return [x for x in al if isinstance(x, dict)]
    if isinstance(al, dict):
        return [al]
    return []


def _attr_by_name(item: dict[str, Any], name: str) -> str | None:
    for a in _attrs_list(item):
        n = a.get("name") or a.get("@name")
        if str(n).lower() == name.lower():
            v = a.get("value") or a.get("@value")
            return str(v) if v is not None else None
    return None


def _categories_from_item(item: dict[str, Any]) -> list[int]:
    out: list[int] = []
    cat = item.get("category")
    if isinstance(cat, list):
        for c in cat:
            if isinstance(c, dict):
                cid = c.get("@attributes", {}).get("id") if isinstance(c.get("@attributes"), dict) else None
            else:
                cid = c
            try:
                out.append(int(str(cid).split("|")[0]))
            except (TypeError, ValueError):
                continue
    elif isinstance(cat, dict):
        cid = cat.get("@attributes", {}).get("id") if isinstance(cat.get("@attributes"), dict) else cat.get("id")
        try:
            out.append(int(str(cid).split("|")[0]))
        except (TypeError, ValueError):
            pass
    elif cat is not None:
        try:
            out.append(int(str(cat).split("|")[0]))
        except (TypeError, ValueError):
            pass
    raw = _attr_by_name(item, "category")
    if raw:
        for part in raw.split("|"):
            try:
                out.append(int(part.strip()))
            except ValueError:
                continue
    return out


def map_newznab_item_to_result(item: dict[str, Any], *, indexer_slug: str) -> BrokerResult | None:
    title = item.get("title")
    if isinstance(title, dict):
        title = title.get("#text") or title.get("text")
    title_s = str(title or "").strip()
    link_raw = item.get("link")
    if isinstance(link_raw, dict):
        url = str(link_raw.get("@href") or link_raw.get("href") or link_raw.get("#text") or "").strip()
    else:
        url = str(link_raw or "").strip()
    enc = item.get("enclosure")
    if not url and isinstance(enc, dict):
        url = str(enc.get("@url") or enc.get("url") or "").strip()
    if not title_s or not url:
        return None
    size_s = _attr_by_name(item, "size") or "0"
    try:
        size = int(size_s)
    except (TypeError, ValueError):
        size = 0
    pub_raw = item.get("pubDate") or item.get("pubdate")
    if isinstance(pub_raw, dict):
        pub_raw = pub_raw.get("#text")
    published_at = _parse_pub_date(str(pub_raw or ""))
    cats = _categories_from_item(item) or [2000]
    return BrokerResult(
        title=title_s,
        url=url,
        magnet=None,
        size=size,
        seeders=None,
        leechers=None,
        protocol="usenet",
        indexer_slug=indexer_slug,
        categories=cats,
        published_at=published_at,
        imdb_id=None,
        info_hash=None,
    )


class NewznabClientBase(BrokerClientBase):
    """Newznab JSON ``t=search`` against a fixed base URL."""

    default_base_url: str = ""

    async def search(
        self,
        query: str,
        categories: list[int],
        limit: int = 50,
        api_key: str = "",
        base_url: str = "",
    ) -> list[BrokerResult]:
        b = self._effective_base(base_url)
        cats = categories if categories else list(self.default_categories)
        return await self._newznab_search(
            b,
            api_key,
            query,
            cats,
            limit,
            indexer_slug=self.slug,
        )

    async def test(self, api_key: str = "", base_url: str = "") -> bool:
        return await self._newznab_test(self._effective_base(base_url), api_key)

    def _effective_base(self, base_url: str) -> str:
        return (base_url or self.default_base_url or "").strip().rstrip("/")

    async def _newznab_search(
        self,
        base: str,
        api_key: str,
        query: str,
        categories: list[int],
        limit: int,
        *,
        indexer_slug: str,
        typed: str = "search",
    ) -> list[BrokerResult]:
        if not base:
            return []
        q = urllib.parse.quote(query.strip() or "", safe="")
        cat_part = ",".join(str(c) for c in categories) if categories else ""
        cat_q = f"&cat={urllib.parse.quote(cat_part, safe=',')}" if cat_part else ""
        url = (
            f"{base}/api?t={typed}&apikey={urllib.parse.quote(api_key)}"
            f"&q={q}&limit={max(1, min(100, limit))}&o=json{cat_q}"
        )
        try:
            async with httpx.AsyncClient(timeout=BROKER_CLIENT_HTTP_TIMEOUT) as client:
                r = await client.get(url, headers={"User-Agent": "MediaMop-Broker/1.0"})
                if r.status_code != 200:
                    return []
                data = r.json()
        except Exception:
            logger.debug("Newznab search failed base=%s", base, exc_info=True)
            return []
        out: list[BrokerResult] = []
        for item in _items_from_newznab_json(data):
            m = map_newznab_item_to_result(item, indexer_slug=indexer_slug)
            if m is not None:
                out.append(m)
        return out[:limit]

    async def _newznab_test(self, base: str, api_key: str) -> bool:
        if not base:
            return False
        key_q = urllib.parse.quote(api_key) if api_key else ""
        url = f"{base}/api?t=caps&apikey={key_q}"
        try:
            async with httpx.AsyncClient(timeout=BROKER_CLIENT_HTTP_TIMEOUT) as client:
                r = await client.get(url, headers={"User-Agent": "MediaMop-Broker/1.0"})
                return r.status_code == 200
        except Exception:
            return False
