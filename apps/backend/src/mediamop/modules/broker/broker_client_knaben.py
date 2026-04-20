"""Knaben.org API native indexer client."""

from __future__ import annotations

import logging
import urllib.parse
from datetime import datetime, timezone

import httpx

from mediamop.modules.broker.broker_client_base import BROKER_CLIENT_HTTP_TIMEOUT, BrokerClientBase
from mediamop.modules.broker.broker_result import BrokerResult

logger = logging.getLogger(__name__)


class BrokerClientKnaben(BrokerClientBase):
    slug = "native__knaben"
    protocol = "torrent"
    display_name = "Knaben"
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
        url = f"https://knaben.org/api/v1?search={q}&size={max(1, min(100, limit))}"
        try:
            async with httpx.AsyncClient(timeout=BROKER_CLIENT_HTTP_TIMEOUT) as client:
                r = await client.get(url, headers={"User-Agent": "MediaMop-Broker/1.0"})
                if r.status_code != 200:
                    return []
                data = r.json()
        except Exception:
            logger.debug("Knaben search failed", exc_info=True)
            return []
        if not isinstance(data, dict):
            return []
        hits = data.get("hits")
        if not isinstance(hits, list):
            return []
        out: list[BrokerResult] = []
        for h in hits:
            if not isinstance(h, dict):
                continue
            name = str(h.get("name") or h.get("title") or "").strip()
            if not name:
                continue
            mag = str(h.get("magnet") or "").strip() or None
            try:
                size = int(h.get("bytes") or h.get("size") or 0)
            except (TypeError, ValueError):
                size = 0
            try:
                seeds = int(h.get("seeders") or 0)
            except (TypeError, ValueError):
                seeds = 0
            try:
                leech = int(h.get("leechers") or 0)
            except (TypeError, ValueError):
                leech = 0
            pub: datetime | None = None
            added = h.get("added") or h.get("date")
            if isinstance(added, (int, float)):
                try:
                    pub = datetime.fromtimestamp(float(added), tz=timezone.utc)
                except (OSError, OverflowError, ValueError):
                    pub = None
            elif isinstance(added, str) and added.strip():
                try:
                    pub = datetime.fromisoformat(added.replace("Z", "+00:00"))
                except ValueError:
                    pub = None
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
                    categories=[8000],
                    published_at=pub,
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
                    "https://knaben.org/api/v1?search=test&size=1",
                    headers={"User-Agent": "MediaMop-Broker/1.0"},
                )
                return r.status_code == 200
        except Exception:
            return False
