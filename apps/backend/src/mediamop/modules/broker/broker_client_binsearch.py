"""Binsearch.info HTML search client."""

from __future__ import annotations

import html
import logging
import re
import urllib.parse
from datetime import datetime, timezone

import httpx

from mediamop.modules.broker.broker_client_base import BROKER_CLIENT_HTTP_TIMEOUT, BrokerClientBase
from mediamop.modules.broker.broker_result import BrokerResult

logger = logging.getLogger(__name__)

_ROW_RE = re.compile(r"<tr class=\"[^\"]*\">.*?</tr>", re.I | re.S)
_TITLE_RE = re.compile(r'<span class="s">(.*?)</span>', re.I | re.S)
_SIZE_RE = re.compile(r"Size:</td><td[^>]*>([^<]+)", re.I)
_DATE_RE = re.compile(r"(\d{4}-\d{2}-\d{2})", re.I)


class BrokerClientBinsearch(BrokerClientBase):
    slug = "native__binsearch"
    protocol = "usenet"
    display_name = "Binsearch"
    requires_api_key = False
    default_categories = [2000, 5000]
    default_base_url = "https://binsearch.info"

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
        url = (
            f"{base}/?q={q}&max={n}&server=&adv_age=&adv_col=on&adv_nfo=on&action=search"
        )
        try:
            async with httpx.AsyncClient(timeout=BROKER_CLIENT_HTTP_TIMEOUT) as client:
                r = await client.get(url, headers={"User-Agent": "MediaMop-Broker/1.0"})
                if r.status_code != 200:
                    return []
                text = r.text
        except Exception:
            logger.debug("Binsearch search failed", exc_info=True)
            return []
        if "xMenuT" not in text:
            return []
        out: list[BrokerResult] = []
        for m in _ROW_RE.finditer(text):
            row = m.group(0)
            tm = _TITLE_RE.search(row)
            if not tm:
                continue
            title = html.unescape(re.sub(r"<[^>]+>", "", tm.group(1)).strip())
            if not title:
                continue
            link_m = re.search(r'href="([^"]+get\.nzb[^"]*)"', row, re.I)
            url = ""
            if link_m:
                href = html.unescape(link_m.group(1).strip())
                url = href if href.startswith("http") else f"{base}/{href.lstrip('/')}"
            if not url:
                continue
            size = 0
            sm = _SIZE_RE.search(row)
            if sm:
                raw_s = sm.group(1).strip()
                size = self._parse_size_human(raw_s)
            pub: datetime | None = None
            dm = _DATE_RE.search(row)
            if dm:
                try:
                    pub = datetime.strptime(dm.group(1), "%Y-%m-%d").replace(tzinfo=timezone.utc)
                except ValueError:
                    pub = None
            out.append(
                BrokerResult(
                    title=title,
                    url=url,
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

    @staticmethod
    def _parse_size_human(raw: str) -> int:
        raw = raw.strip().upper().replace(",", "")
        m = re.match(r"([\d.]+)\s*([KMGT])?B?", raw)
        if not m:
            return 0
        try:
            num = float(m.group(1))
        except ValueError:
            return 0
        unit = (m.group(2) or "").upper()
        mult = {"K": 1024, "M": 1024**2, "G": 1024**3, "T": 1024**4}.get(unit, 1)
        return int(num * mult)

    async def test(self, api_key: str = "", base_url: str = "") -> bool:
        _ = api_key
        base = (base_url or self.default_base_url or "").strip().rstrip("/")
        if not base:
            return False
        try:
            async with httpx.AsyncClient(timeout=BROKER_CLIENT_HTTP_TIMEOUT) as client:
                r = await client.get(
                    f"{base}/?q=test&max=1&action=search",
                    headers={"User-Agent": "MediaMop-Broker/1.0"},
                )
                return r.status_code == 200 and "xMenuT" in r.text
        except Exception:
            return False
