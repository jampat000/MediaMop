"""Unified Torznab/Newznab proxy endpoints for *arr → Broker."""

from __future__ import annotations

import json
from typing import Annotated
from xml.sax.saxutils import escape

from fastapi import APIRouter, HTTPException, Query, Response
from starlette import status

from mediamop.api.deps import DbSessionDep, SettingsDep
from mediamop.core.config import MediaMopSettings
from mediamop.modules.broker.broker_result import BrokerResult
from mediamop.modules.broker.broker_schemas import BrokerSettingsOut, BrokerSettingsRotateIn
from mediamop.modules.broker.broker_search_service import federated_search
from mediamop.modules.broker.broker_settings_service import get_proxy_api_key, rotate_proxy_api_key
from mediamop.platform.auth.authorization import RequireOperatorDep
from mediamop.platform.auth.csrf import verify_csrf_token

router = APIRouter(tags=["broker-proxy"])


def _csrf(settings: MediaMopSettings, token: str) -> None:
    secret = settings.session_secret or ""
    if not verify_csrf_token(secret, token):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid CSRF token.")


TORZNAB_NS = "http://torznab.com/schemas/2010/feed"


def _torznab_caps_xml() -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        "<caps>"
        '<server version="1.0" title="MediaMop Broker"/>'
        "<searching>"
        '<search available="yes"/>'
        '<tv-search available="yes"/>'
        '<movie-search available="yes"/>'
        "</searching>"
        "</caps>"
    )


def _newznab_caps_json() -> str:
    return json.dumps({"caps": {"server": [{"@version": "1.0", "@title": "MediaMop Broker"}]}})


def _validate_proxy_key(db, apikey: str | None) -> None:
    expected = (get_proxy_api_key(db) or "").strip()
    got = (apikey or "").strip()
    if not got or got != expected:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or missing API key.")


def _torznab_rss(results: list[BrokerResult]) -> str:
    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        f'<rss version="2.0" xmlns:torznab="{TORZNAB_NS}">',
        "<channel>",
        "<title>MediaMop Broker Torznab</title>",
        "<description>Broker unified Torznab proxy</description>",
    ]
    for r in results:
        lines.append("<item>")
        lines.append(f"<title>{escape(r.title)}</title>")
        lines.append(f"<guid>{escape(r.url)}</guid>")
        lines.append(f"<link>{escape(r.url)}</link>")
        if r.published_at is not None:
            lines.append(f"<pubDate>{r.published_at.strftime('%a, %d %b %Y %H:%M:%S GMT')}</pubDate>")
        enc_type = "application/x-bittorrent"
        if r.url.startswith("magnet:"):
            enc_type = "application/x-bittorrent"
        lines.append(
            f'<enclosure url="{escape(r.url)}" length="{int(r.size)}" type="{escape(enc_type)}"/>',
        )
        lines.append(f'<torznab:attr name="size" value="{int(r.size)}"/>')
        if r.seeders is not None:
            lines.append(f'<torznab:attr name="seeders" value="{int(r.seeders)}"/>')
        if r.leechers is not None:
            lines.append(f'<torznab:attr name="peers" value="{int(r.leechers)}"/>')
        if r.info_hash:
            lines.append(f'<torznab:attr name="infohash" value="{escape(r.info_hash.lower())}"/>')
        lines.append("</item>")
    lines.extend(["</channel>", "</rss>"])
    return "\n".join(lines)


def _newznab_json(results: list[BrokerResult]) -> dict[str, object]:
    items: list[dict[str, object]] = []
    for r in results:
        cat_id = str(r.categories[0]) if r.categories else "2000"
        items.append(
            {
                "title": r.title,
                "link": r.url,
                "pubDate": r.published_at.isoformat() if r.published_at else "",
                "category": {"@attributes": {"id": cat_id}},
                "enclosure": {"@url": r.url, "@length": str(int(r.size))},
                "attr": [
                    {"@attributes": {"name": "size", "value": str(int(r.size))}},
                ],
            },
        )
    return {"channel": {"item": items}}


@router.get("/torznab")
async def broker_torznab_proxy(
    db: DbSessionDep,
    apikey: Annotated[str | None, Query()] = None,
    t: Annotated[str | None, Query()] = None,
    q: Annotated[str | None, Query()] = None,
    cat: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> Response:
    _ = cat
    _validate_proxy_key(db, apikey)
    tl = (t or "search").lower()
    if tl == "caps":
        return Response(content=_torznab_caps_xml(), media_type="application/xml; charset=utf-8")
    if tl != "search":
        return Response(content=_torznab_rss([]), media_type="application/rss+xml; charset=utf-8")
    query = (q or "").strip()
    if not query:
        return Response(content=_torznab_rss([]), media_type="application/rss+xml")
    results = await federated_search(
        db,
        query=query,
        media_type="all",
        indexer_ids=None,
        limit_per_indexer=limit,
        timeout_seconds=10.0,
        protocol_filter="torrent",
    )
    return Response(content=_torznab_rss(results), media_type="application/rss+xml; charset=utf-8")


@router.get("/newznab")
async def broker_newznab_proxy(
    db: DbSessionDep,
    apikey: Annotated[str | None, Query()] = None,
    t: Annotated[str | None, Query()] = None,
    q: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> Response:
    _validate_proxy_key(db, apikey)
    tl = (t or "search").lower()
    if tl == "caps":
        return Response(content=_newznab_caps_json(), media_type="application/json; charset=utf-8")
    if tl != "search":
        return Response(content=json.dumps({"channel": {"item": []}}), media_type="application/json; charset=utf-8")
    query = (q or "").strip()
    if not query:
        return Response(content=json.dumps({"channel": {"item": []}}), media_type="application/json")
    results = await federated_search(
        db,
        query=query,
        media_type="all",
        indexer_ids=None,
        limit_per_indexer=limit,
        timeout_seconds=10.0,
        protocol_filter="usenet",
    )
    body = json.dumps(_newznab_json(results))
    return Response(content=body, media_type="application/json; charset=utf-8")


@router.get("/proxy/apikey", response_model=BrokerSettingsOut)
def get_broker_proxy_api_key_display(
    _user: RequireOperatorDep,
    db: DbSessionDep,
) -> BrokerSettingsOut:
    return BrokerSettingsOut(proxy_api_key=get_proxy_api_key(db))


@router.post("/proxy/apikey/rotate", response_model=BrokerSettingsOut)
def post_broker_proxy_api_key_rotate(
    _user: RequireOperatorDep,
    db: DbSessionDep,
    settings: SettingsDep,
    body: BrokerSettingsRotateIn,
) -> BrokerSettingsOut:
    _csrf(settings, body.csrf_token)
    new_key = rotate_proxy_api_key(db)
    return BrokerSettingsOut(proxy_api_key=new_key)
