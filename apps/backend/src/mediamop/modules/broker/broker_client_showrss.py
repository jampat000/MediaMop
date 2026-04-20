"""showRSS.info RSS native indexer client (client-side title filter)."""

from __future__ import annotations

from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

from mediamop.modules.broker.broker_client_base import BrokerClientBase, rss_channel_items
from mediamop.modules.broker.broker_result import BrokerResult


class BrokerClientShowrss(BrokerClientBase):
    slug = "native__showrss"
    protocol = "torrent"
    display_name = "showRSS"
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
        q = (query.strip() or "").lower()
        url = "https://showrss.info/other/all.rss"
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
                    categories=[5000],
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
        raw = await self._get_bytes("https://showrss.info/other/all.rss")
        return raw is not None and b"<rss" in raw[:4000].lower()
