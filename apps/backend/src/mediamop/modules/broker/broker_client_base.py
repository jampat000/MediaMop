"""Abstract base for Broker native / generic indexer HTTP clients."""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any
from xml.etree import ElementTree

import httpx

from mediamop.modules.broker.broker_result import BrokerResult

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

BROKER_CLIENT_HTTP_TIMEOUT = httpx.Timeout(10.0)


def rss_channel_items(xml_bytes: bytes) -> list[dict[str, Any]]:
    """Parse RSS/Atom-ish XML into a list of per-item dicts (best-effort, no network)."""

    out: list[dict[str, Any]] = []
    try:
        root = ElementTree.fromstring(xml_bytes)
    except ElementTree.ParseError:
        return out
    channel = root.find("channel")
    if channel is None:
        items = root.findall(".//{http://www.w3.org/2005/Atom}entry")
        if items:
            ns = {"atom": "http://www.w3.org/2005/Atom"}
            for el in items:
                title_el = el.find("atom:title", ns)
                link_el = el.find("atom:link", ns)
                title = (title_el.text or "").strip() if title_el is not None and title_el.text else ""
                href = link_el.get("href", "").strip() if link_el is not None else ""
                out.append({"title": title, "link": href, "raw": el})
        return out
    for item in channel.findall("item"):
        title_el = item.find("title")
        link_el = item.find("link")
        guid_el = item.find("guid")
        pub_el = item.find("pubDate")
        enclosure = item.find("enclosure")
        title = (title_el.text or "").strip() if title_el is not None and title_el.text else ""
        link = (link_el.text or "").strip() if link_el is not None and link_el.text else ""
        guid = (guid_el.text or "").strip() if guid_el is not None and guid_el.text else ""
        pub = (pub_el.text or "").strip() if pub_el is not None and pub_el.text else ""
        enc_url = enclosure.get("url", "").strip() if enclosure is not None else ""
        enc_type = enclosure.get("type", "").strip() if enclosure is not None else ""
        extras: dict[str, str] = {}
        for child in list(item):
            tag = child.tag
            local = tag.split("}", 1)[-1] if "}" in tag else tag
            if (child.text or "").strip():
                extras[local] = (child.text or "").strip()
            for attr_name, attr_val in (child.attrib or {}).items():
                extras[f"{local}:{attr_name}"] = str(attr_val)
        desc_el = item.find("description")
        description = (desc_el.text or "").strip() if desc_el is not None and desc_el.text else ""
        out.append(
            {
                "title": title,
                "link": link,
                "guid": guid,
                "pubDate": pub,
                "enclosure_url": enc_url,
                "enclosure_type": enc_type,
                "description": description,
                "extras": extras,
                "raw": item,
            },
        )
    return out


class BrokerClientBase(ABC):
    """One indexer integration — async search/test over HTTP (httpx)."""

    slug: str = ""
    protocol: str = "torrent"
    display_name: str = ""
    requires_api_key: bool = False
    default_categories: list[int]

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        if "default_categories" not in cls.__dict__ or cls.default_categories is None:
            cls.default_categories = []

    @abstractmethod
    async def search(
        self,
        query: str,
        categories: list[int],
        limit: int = 50,
        api_key: str = "",
        base_url: str = "",
    ) -> list[BrokerResult]:
        raise NotImplementedError

    @abstractmethod
    async def test(
        self,
        api_key: str = "",
        base_url: str = "",
    ) -> bool:
        raise NotImplementedError

    async def _get_bytes(self, url: str) -> bytes | None:
        try:
            async with httpx.AsyncClient(timeout=BROKER_CLIENT_HTTP_TIMEOUT) as client:
                r = await client.get(url, headers={"User-Agent": "MediaMop-Broker/1.0"})
                if r.status_code != 200:
                    return None
                return r.content
        except Exception:
            logger.debug("Broker client GET failed url=%s", url, exc_info=True)
            return None

    async def _get_text(self, url: str) -> str | None:
        raw = await self._get_bytes(url)
        if raw is None:
            return None
        try:
            return raw.decode("utf-8", errors="replace")
        except Exception:
            return None

    async def _get_json(self, url: str) -> Any:
        try:
            async with httpx.AsyncClient(timeout=BROKER_CLIENT_HTTP_TIMEOUT) as client:
                r = await client.get(url, headers={"User-Agent": "MediaMop-Broker/1.0"})
                if r.status_code != 200:
                    return None
                return r.json()
        except Exception:
            logger.debug("Broker client JSON GET failed url=%s", url, exc_info=True)
            return None

    async def _post_json(self, url: str, *, json_body: dict[str, Any]) -> Any:
        try:
            async with httpx.AsyncClient(timeout=BROKER_CLIENT_HTTP_TIMEOUT) as client:
                r = await client.post(
                    url,
                    json=json_body,
                    headers={"User-Agent": "MediaMop-Broker/1.0"},
                )
                if r.status_code != 200:
                    return None
                return r.json()
        except Exception:
            logger.debug("Broker client POST failed url=%s", url, exc_info=True)
            return None
