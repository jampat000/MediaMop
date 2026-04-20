"""Internet Archive advanced search API client."""

from __future__ import annotations

import logging
import urllib.parse

import httpx

from mediamop.modules.broker.broker_client_base import BROKER_CLIENT_HTTP_TIMEOUT, BrokerClientBase
from mediamop.modules.broker.broker_result import BrokerResult

logger = logging.getLogger(__name__)


class BrokerClientInternetarchive(BrokerClientBase):
    slug = "native__internetarchive"
    protocol = "torrent"
    display_name = "Internet Archive"
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
        url = (
            "https://archive.org/advancedsearch.php?"
            f"q={q}&fl[]=identifier,title,mediatype,downloads&rows={n}&output=json"
        )
        try:
            async with httpx.AsyncClient(timeout=BROKER_CLIENT_HTTP_TIMEOUT) as client:
                r = await client.get(url, headers={"User-Agent": "MediaMop-Broker/1.0"})
                if r.status_code != 200:
                    return []
                data = r.json()
        except Exception:
            logger.debug("IA search failed", exc_info=True)
            return []
        if not isinstance(data, dict):
            return []
        resp = data.get("response")
        if not isinstance(resp, dict):
            return []
        docs = resp.get("docs")
        if not isinstance(docs, list):
            return []
        out: list[BrokerResult] = []
        for d in docs:
            if not isinstance(d, dict):
                continue
            ident = str(d.get("identifier") or "").strip()
            title = str(d.get("title") or ident).strip()
            if not ident or not title:
                continue
            turl = f"https://archive.org/download/{ident}/{ident}.torrent"
            out.append(
                BrokerResult(
                    title=title,
                    url=turl,
                    magnet=None,
                    size=0,
                    seeders=None,
                    leechers=None,
                    protocol="torrent",
                    indexer_slug=self.slug,
                    categories=[8000],
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
                    "https://archive.org/advancedsearch.php?q=test&fl[]=identifier&rows=1&output=json",
                    headers={"User-Agent": "MediaMop-Broker/1.0"},
                )
                return r.status_code == 200
        except Exception:
            return False
