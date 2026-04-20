"""LimeTorrents RSS native indexer client."""

from __future__ import annotations

import re
import urllib.parse
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

from mediamop.modules.broker.broker_client_base import BrokerClientBase, rss_channel_items
from mediamop.modules.broker.broker_result import BrokerResult

_SIZE_RE = re.compile(r"Size:\s*([\d,.]+)\s*([KMG]?)B", re.I)


class BrokerClientLimetorrents(BrokerClientBase):
    slug = "native__limetorrents"
    protocol = "torrent"
    display_name = "LimeTorrents"
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
        q = (query.strip() or "").lower()
        url = "https://www.limetorrents.lol/rss/16/"
        raw = await self._get_bytes(url)
        if raw is None:
            return []
        items = rss_channel_items(raw)
        out: list[BrokerResult] = []
        for it in items:
            title = str(it.get("title") or "").strip()
            link = str(it.get("link") or it.get("enclosure_url") or "").strip()
            if not title or not link:
                continue
            if q and q not in title.lower():
                continue
            desc = str(it.get("description") or "")
            size = 0
            m = _SIZE_RE.search(desc)
            if m:
                try:
                    num = float(m.group(1).replace(",", ""))
                    unit = (m.group(2) or "").upper()
                    mult = {"K": 1024, "M": 1024**2, "G": 1024**3}.get(unit, 1)
                    size = int(num * mult)
                except (TypeError, ValueError):
                    size = 0
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
                    size=size,
                    seeders=None,
                    leechers=None,
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
        raw = await self._get_bytes("https://www.limetorrents.lol/rss/16/")
        return raw is not None and b"<rss" in raw[:4000].lower()
