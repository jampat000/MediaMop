"""NZBIndex JSON search API client."""

from __future__ import annotations

import logging
import urllib.parse
from datetime import datetime, timezone
from typing import Any

import httpx

from mediamop.modules.broker.broker_client_base import BROKER_CLIENT_HTTP_TIMEOUT, BrokerClientBase
from mediamop.modules.broker.broker_result import BrokerResult

logger = logging.getLogger(__name__)


def _parse_ts(val: Any) -> datetime | None:
    if val is None:
        return None
    if isinstance(val, (int, float)):
        try:
            return datetime.fromtimestamp(float(val), tz=timezone.utc)
        except (OSError, OverflowError, ValueError):
            return None
    s = str(val).strip()
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None


class BrokerClientNzbindex(BrokerClientBase):
    slug = "native__nzbindex"
    protocol = "usenet"
    display_name = "NZBIndex"
    requires_api_key = False
    default_categories = [2000, 5000]
    default_base_url = "https://nzbindex.com"

    async def search(
        self,
        query: str,
        categories: list[int],
        limit: int = 50,
        api_key: str = "",
        base_url: str = "",
    ) -> list[BrokerResult]:
        _ = categories, api_key
        base = (base_url or self.default_base_url or "").strip().rstrip("/")
        if not base:
            return []
        q = urllib.parse.quote(query.strip() or "", safe="")
        n = max(1, min(100, limit))
        url = f"{base}/api/?q={q}&max={n}&more=1&hidespam=1&output=json"
        try:
            async with httpx.AsyncClient(timeout=BROKER_CLIENT_HTTP_TIMEOUT) as client:
                r = await client.get(url, headers={"User-Agent": "MediaMop-Broker/1.0"})
                if r.status_code != 200:
                    return []
                data = r.json()
        except Exception:
            logger.debug("NZBIndex search failed", exc_info=True)
            return []
        if not isinstance(data, dict):
            return []
        results = data.get("results") or data.get("items") or data.get("releases")
        if not isinstance(results, list):
            return []
        out: list[BrokerResult] = []
        for row in results:
            if not isinstance(row, dict):
                continue
            title = str(row.get("title") or row.get("name") or "").strip()
            link = str(row.get("link") or row.get("url") or row.get("nzb") or "").strip()
            if not title or not link:
                continue
            try:
                size = int(row.get("size") or row.get("bytes") or 0)
            except (TypeError, ValueError):
                size = 0
            pub = _parse_ts(row.get("posted") or row.get("pubDate") or row.get("date"))
            out.append(
                BrokerResult(
                    title=title,
                    url=link,
                    magnet=None,
                    size=size,
                    seeders=None,
                    leechers=None,
                    protocol="usenet",
                    indexer_slug=self.slug,
                    categories=[2000, 5000],
                    published_at=pub,
                    imdb_id=None,
                    info_hash=None,
                ),
            )
            if len(out) >= limit:
                break
        return out

    async def test(self, api_key: str = "", base_url: str = "") -> bool:
        _ = api_key
        base = (base_url or self.default_base_url or "").strip().rstrip("/")
        if not base:
            return False
        try:
            async with httpx.AsyncClient(timeout=BROKER_CLIENT_HTTP_TIMEOUT) as client:
                r = await client.get(
                    f"{base}/api/?q=test&max=1&more=1&hidespam=1&output=json",
                    headers={"User-Agent": "MediaMop-Broker/1.0"},
                )
                return r.status_code == 200
        except Exception:
            return False
