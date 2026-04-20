"""EZTV native indexer client."""

from __future__ import annotations

import logging
import urllib.parse

import httpx

from mediamop.modules.broker.broker_client_base import BROKER_CLIENT_HTTP_TIMEOUT, BrokerClientBase
from mediamop.modules.broker.broker_result import BrokerResult

logger = logging.getLogger(__name__)


class BrokerClientEztv(BrokerClientBase):
    slug = "native__eztv"
    protocol = "torrent"
    display_name = "EZTV"
    requires_api_key = False
    default_categories = [5000]

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
        url = f"https://eztv.re/api/get-torrents?limit={max(1, min(100, limit))}&keywords={q}"
        try:
            async with httpx.AsyncClient(timeout=BROKER_CLIENT_HTTP_TIMEOUT) as client:
                r = await client.get(url, headers={"User-Agent": "MediaMop-Broker/1.0"})
                if r.status_code != 200:
                    return []
                data = r.json()
        except Exception:
            logger.debug("EZTV search failed", exc_info=True)
            return []
        out: list[BrokerResult] = []
        if not isinstance(data, dict):
            return out
        torrents = data.get("torrents")
        if not isinstance(torrents, list):
            return out
        for t in torrents:
            if not isinstance(t, dict):
                continue
            title = str(t.get("title") or "").strip()
            if not title:
                continue
            mag = str(t.get("magnet_url") or "").strip() or None
            try:
                size = int(t.get("size_bytes") or 0)
            except (TypeError, ValueError):
                size = 0
            try:
                seeds = int(t.get("seeds") or 0)
            except (TypeError, ValueError):
                seeds = 0
            out.append(
                BrokerResult(
                    title=title,
                    url=mag or "",
                    magnet=mag,
                    size=size,
                    seeders=seeds,
                    leechers=None,
                    protocol="torrent",
                    indexer_slug=self.slug,
                    categories=[5000],
                    published_at=None,
                    imdb_id=None,
                    info_hash=None,
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
                    "https://eztv.re/api/get-torrents?limit=1",
                    headers={"User-Agent": "MediaMop-Broker/1.0"},
                )
                return r.status_code == 200
        except Exception:
            return False
