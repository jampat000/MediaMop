"""YTS.mx native indexer client."""

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


class BrokerClientYts(BrokerClientBase):
    slug = "native__yts"
    protocol = "torrent"
    display_name = "YTS"
    requires_api_key = False
    default_categories = [2000]

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
        url = f"https://yts.mx/api/v2/list_movies.json?query_term={q}&limit={max(1, min(50, limit))}"
        try:
            async with httpx.AsyncClient(timeout=BROKER_CLIENT_HTTP_TIMEOUT) as client:
                r = await client.get(url, headers={"User-Agent": "MediaMop-Broker/1.0"})
                if r.status_code != 200:
                    return []
                data = r.json()
        except Exception:
            logger.debug("YTS search failed", exc_info=True)
            return []
        out: list[BrokerResult] = []
        if not isinstance(data, dict):
            return out
        d = data.get("data")
        if not isinstance(d, dict):
            return out
        movies = d.get("movies")
        if not isinstance(movies, list):
            return out
        for m in movies:
            if not isinstance(m, dict):
                continue
            title = str(m.get("title_english") or m.get("title") or "").strip()
            if not title:
                continue
            imdb = str(m.get("imdb_code") or "").strip() or None
            torrents = m.get("torrents")
            if not isinstance(torrents, list) or not torrents:
                continue
            t0 = torrents[0]
            if not isinstance(t0, dict):
                continue
            h = str(t0.get("hash") or "").strip().lower()
            mag = _magnet(h, title) or None
            try:
                size = int(t0.get("size_bytes") or 0)
            except (TypeError, ValueError):
                size = 0
            try:
                seeds = int(t0.get("seeds") or 0)
            except (TypeError, ValueError):
                seeds = 0
            url_t = str(t0.get("url") or "").strip()
            out.append(
                BrokerResult(
                    title=title,
                    url=mag or url_t or "",
                    magnet=mag,
                    size=size,
                    seeders=seeds,
                    leechers=None,
                    protocol="torrent",
                    indexer_slug=self.slug,
                    categories=[2000],
                    published_at=None,
                    imdb_id=imdb,
                    info_hash=h or None,
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
                    "https://yts.mx/api/v2/list_movies.json?limit=1",
                    headers={"User-Agent": "MediaMop-Broker/1.0"},
                )
                return r.status_code == 200
        except Exception:
            return False
