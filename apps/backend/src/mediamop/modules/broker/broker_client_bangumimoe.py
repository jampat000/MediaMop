"""Bangumi.moe torrent search API client."""

from __future__ import annotations

import logging

import httpx

from mediamop.modules.broker.broker_client_base import BROKER_CLIENT_HTTP_TIMEOUT, BrokerClientBase
from mediamop.modules.broker.broker_result import BrokerResult

logger = logging.getLogger(__name__)


class BrokerClientBangumimoe(BrokerClientBase):
    slug = "native__bangumimoe"
    protocol = "torrent"
    display_name = "Bangumi Moe"
    requires_api_key = False
    default_categories = [5070]

    async def search(
        self,
        query: str,
        categories: list[int],
        limit: int = 50,
        api_key: str = "",
        base_url: str = "",
    ) -> list[BrokerResult]:
        _ = categories, api_key, base_url
        body = {"query": query.strip() or "", "page_num": 1, "page_size": max(1, min(100, limit))}
        try:
            async with httpx.AsyncClient(timeout=BROKER_CLIENT_HTTP_TIMEOUT) as client:
                r = await client.post(
                    "https://bangumi.moe/api/torrent/search",
                    json=body,
                    headers={"User-Agent": "MediaMop-Broker/1.0"},
                )
                if r.status_code != 200:
                    return []
                data = r.json()
        except Exception:
            logger.debug("Bangumi search failed", exc_info=True)
            return []
        if not isinstance(data, dict):
            return []
        torrents = data.get("torrents")
        if not isinstance(torrents, list):
            return []
        out: list[BrokerResult] = []
        for t in torrents:
            if not isinstance(t, dict):
                continue
            title = str(t.get("title") or "").strip()
            mag = str(t.get("magnet") or t.get("magnet_uri") or "").strip() or None
            if not title:
                continue
            try:
                size = int(t.get("size") or 0)
            except (TypeError, ValueError):
                size = 0
            team = t.get("team_id")
            if team is not None:
                title = f"{title} [{team}]"
            out.append(
                BrokerResult(
                    title=title,
                    url=mag or "",
                    magnet=mag,
                    size=size,
                    seeders=None,
                    leechers=None,
                    protocol="torrent",
                    indexer_slug=self.slug,
                    categories=[5070],
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
                r = await client.post(
                    "https://bangumi.moe/api/torrent/search",
                    json={"query": "test", "page_num": 1, "page_size": 1},
                    headers={"User-Agent": "MediaMop-Broker/1.0"},
                )
                return r.status_code == 200
        except Exception:
            return False
