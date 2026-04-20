"""BT4G RSS native indexer client (movie + TV feeds merged)."""

from __future__ import annotations

import urllib.parse
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

from mediamop.modules.broker.broker_client_base import BrokerClientBase, rss_channel_items
from mediamop.modules.broker.broker_result import BrokerResult


class BrokerClientBt4g(BrokerClientBase):
    slug = "native__bt4g"
    protocol = "torrent"
    display_name = "BT4G"
    requires_api_key = False
    default_categories = [8000]

    async def _parse_feed(self, raw: bytes | None, cats: list[int]) -> list[BrokerResult]:
        if raw is None:
            return []
        items = rss_channel_items(raw)
        out: list[BrokerResult] = []
        for it in items:
            title = str(it.get("title") or "").strip()
            link = str(it.get("link") or it.get("enclosure_url") or "").strip()
            if not title or not link:
                continue
            pub: datetime | None = None
            praw = str(it.get("pubDate") or "").strip()
            if praw:
                try:
                    pub = parsedate_to_datetime(praw)
                    if pub.tzinfo is None:
                        pub = pub.replace(tzinfo=timezone.utc)
                except (TypeError, ValueError, OverflowError):
                    pub = None
            out.append(
                BrokerResult(
                    title=title,
                    url=link,
                    magnet=None,
                    size=0,
                    seeders=None,
                    leechers=None,
                    protocol="torrent",
                    indexer_slug=self.slug,
                    categories=cats,
                    published_at=pub,
                    imdb_id=None,
                    info_hash=None,
                ),
            )
        return out

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
        url_m = f"https://bt4gprx.com/search?q={q}&category=movie&p=1&orderby=seeders&fmt=rss"
        url_s = f"https://bt4gprx.com/search?q={q}&category=show&p=1&orderby=seeders&fmt=rss"
        raw_m = await self._get_bytes(url_m)
        raw_s = await self._get_bytes(url_s)
        merged = await self._parse_feed(raw_m, [2000]) + await self._parse_feed(raw_s, [5000])
        return merged[:limit]

    async def test(self, api_key: str = "", base_url: str = "") -> bool:
        _ = api_key, base_url
        raw = await self._get_bytes(
            "https://bt4gprx.com/search?q=test&category=movie&p=1&orderby=seeders&fmt=rss",
        )
        return raw is not None and b"<rss" in raw[:4000].lower()
