"""Academic Torrents API client."""

from __future__ import annotations

import logging
import urllib.parse
import httpx

from mediamop.modules.broker.broker_client_base import BROKER_CLIENT_HTTP_TIMEOUT, BrokerClientBase
from mediamop.modules.broker.broker_result import BrokerResult

logger = logging.getLogger(__name__)


class BrokerClientAcademictorrents(BrokerClientBase):
    slug = "native__academictorrents"
    protocol = "torrent"
    display_name = "Academic Torrents"
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
        n = max(1, min(100, limit))
        url = f"https://academictorrents.com/apiv2/torrents?query={q}&limit={n}"
        try:
            async with httpx.AsyncClient(timeout=BROKER_CLIENT_HTTP_TIMEOUT) as client:
                r = await client.get(url, headers={"User-Agent": "MediaMop-Broker/1.0"})
                if r.status_code != 200:
                    return []
                data = r.json()
        except Exception:
            logger.debug("AcademicTorrents search failed", exc_info=True)
            return []
        if not isinstance(data, list):
            return []
        out: list[BrokerResult] = []
        for row in data:
            if not isinstance(row, dict):
                continue
            name = str(row.get("name") or row.get("title") or "").strip()
            if not name:
                continue
            ih = str(row.get("info_hash") or row.get("hash") or "").strip().lower() or None
            try:
                size = int(row.get("size") or 0)
            except (TypeError, ValueError):
                size = 0
            try:
                seeds = int(row.get("seeders") or row.get("seeds") or 0)
            except (TypeError, ValueError):
                seeds = 0
            turl = str(row.get("url") or row.get("link") or "").strip()
            out.append(
                BrokerResult(
                    title=name,
                    url=turl,
                    magnet=None,
                    size=size,
                    seeders=seeds,
                    leechers=None,
                    protocol="torrent",
                    indexer_slug=self.slug,
                    categories=[8000],
                    published_at=None,
                    imdb_id=None,
                    info_hash=ih,
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
                    "https://academictorrents.com/apiv2/torrents?query=test&limit=1",
                    headers={"User-Agent": "MediaMop-Broker/1.0"},
                )
                return r.status_code == 200
        except Exception:
            return False
