"""The Pirate Bay (apibay.org) native indexer client."""

from __future__ import annotations

import logging
import urllib.parse
from typing import Any

import httpx

from mediamop.modules.broker.broker_client_base import BROKER_CLIENT_HTTP_TIMEOUT, BrokerClientBase
from mediamop.modules.broker.broker_result import BrokerResult

logger = logging.getLogger(__name__)


def _magnet(info_hash: str, name: str) -> str:
    h = (info_hash or "").strip().lower()
    if len(h) != 40:
        return ""
    dn = urllib.parse.quote(name or "torrent", safe="")
    return f"magnet:?xt=urn:btih:{h}&dn={dn}"


def _cat_for_type(type_id: Any) -> list[int]:
    try:
        tid = int(type_id)
    except (TypeError, ValueError):
        return [8000]
    if tid == 200:
        return [2000]
    if tid == 500:
        return [5000]
    return [8000]


class BrokerClientThepiratebay(BrokerClientBase):
    slug = "native__thepiratebay"
    protocol = "torrent"
    display_name = "The Pirate Bay"
    requires_api_key = False
    default_categories = [8000]

    async def search(
        self,
        query: str,
        categories: list[int],
        limit: int = 50,
        api_key: str = "",
        base_url: str = "",
    ) -> list[BrokerResult]:
        _ = categories, api_key, base_url
        q = urllib.parse.quote(query.strip() or "", safe="")
        url = f"https://apibay.org/q.php?q={q}&cat=0"
        try:
            async with httpx.AsyncClient(timeout=BROKER_CLIENT_HTTP_TIMEOUT) as client:
                r = await client.get(url, headers={"User-Agent": "MediaMop-Broker/1.0"})
                if r.status_code != 200:
                    return []
                data = r.json()
        except Exception:
            logger.debug("TPB search failed", exc_info=True)
            return []
        if not isinstance(data, list):
            return []
        out: list[BrokerResult] = []
        for row in data:
            if not isinstance(row, dict):
                continue
            name = str(row.get("name") or "").strip()
            if not name:
                continue
            ih = str(row.get("info_hash") or "").strip().lower()
            mag = _magnet(ih, name) or None
            try:
                size = int(row.get("size") or 0)
            except (TypeError, ValueError):
                size = 0
            try:
                seeds = int(row.get("seeders") or 0)
            except (TypeError, ValueError):
                seeds = 0
            try:
                leech = int(row.get("leechers") or 0)
            except (TypeError, ValueError):
                leech = 0
            cats = _cat_for_type(row.get("category"))
            out.append(
                BrokerResult(
                    title=name,
                    url=mag or "",
                    magnet=mag,
                    size=size,
                    seeders=seeds,
                    leechers=leech,
                    protocol="torrent",
                    indexer_slug=self.slug,
                    categories=cats,
                    published_at=None,
                    imdb_id=None,
                    info_hash=ih or None,
                ),
            )
            if len(out) >= limit:
                break
        return out

    async def test(self, api_key: str = "", base_url: str = "") -> bool:
        _ = api_key, base_url
        try:
            async with httpx.AsyncClient(timeout=BROKER_CLIENT_HTTP_TIMEOUT) as client:
                r = await client.get(
                    "https://apibay.org/q.php?q=test",
                    headers={"User-Agent": "MediaMop-Broker/1.0"},
                )
                if r.status_code != 200:
                    return False
                data = r.json()
                return isinstance(data, list) and len(data) > 0
        except Exception:
            return False
