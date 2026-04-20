"""Federated async search across enabled Broker indexers."""

from __future__ import annotations

import asyncio
import logging
from typing import Literal

from sqlalchemy import select
from sqlalchemy.orm import Session

from mediamop.modules.broker.broker_client_registry import get_client_for_indexer
from mediamop.modules.broker.broker_indexers_model import BrokerIndexerRow
from mediamop.modules.broker.broker_result import BrokerResult, deduplicate_results, sort_results

logger = logging.getLogger(__name__)

ProtocolFilter = Literal["all", "torrent", "usenet"]


def _category_codes_for_media(media_type: str) -> list[int]:
    m = (media_type or "all").strip().lower()
    if m == "tv":
        return [5000, 5070]
    if m in ("movie", "movies"):
        return [2000]
    return []


def _torrent_lane_indexer(row: BrokerIndexerRow) -> bool:
    k = (row.kind or "").strip().lower()
    p = (row.protocol or "").strip().lower()
    return p == "torrent" or k == "torznab"


def _usenet_lane_indexer(row: BrokerIndexerRow) -> bool:
    k = (row.kind or "").strip().lower()
    p = (row.protocol or "").strip().lower()
    return p == "usenet" or k == "newznab"


async def federated_search(
    session: Session,
    *,
    query: str,
    media_type: str = "all",
    indexer_ids: list[int] | None = None,
    limit_per_indexer: int = 50,
    timeout_seconds: float = 10.0,
    protocol_filter: ProtocolFilter = "all",
) -> list[BrokerResult]:
    stmt = select(BrokerIndexerRow).where(BrokerIndexerRow.enabled == 1).order_by(
        BrokerIndexerRow.priority,
        BrokerIndexerRow.id,
    )
    rows = list(session.scalars(stmt).all())
    if indexer_ids is not None and indexer_ids:
        wanted = {int(x) for x in indexer_ids}
        rows = [r for r in rows if int(r.id) in wanted]
    if protocol_filter == "torrent":
        rows = [r for r in rows if _torrent_lane_indexer(r)]
    elif protocol_filter == "usenet":
        rows = [r for r in rows if _usenet_lane_indexer(r)]

    cats = _category_codes_for_media(media_type)
    q = (query or "").strip()
    if not q:
        return []

    async def _run_one(row: BrokerIndexerRow) -> list[BrokerResult]:
        client = get_client_for_indexer(row)
        if client is None:
            return []
        try:
            return await asyncio.wait_for(
                client.search(
                    q,
                    cats,
                    limit=max(1, min(100, limit_per_indexer)),
                    api_key=(row.api_key or ""),
                    base_url=(row.url or ""),
                ),
                timeout=timeout_seconds,
            )
        except Exception:
            logger.debug("Indexer search failed slug=%s", row.slug, exc_info=True)
            return []

    tasks = [_run_one(r) for r in rows]
    parts = await asyncio.gather(*tasks)
    merged: list[BrokerResult] = []
    for chunk in parts:
        merged.extend(chunk)
    merged = deduplicate_results(merged)
    return sort_results(merged)


def sort_tv_before_movies_for_mixed(results: list[BrokerResult]) -> list[BrokerResult]:
    """When ``media_type`` is ``all``, order TV-tagged rows before movie-tagged rows (stable within tiers)."""

    def _pub_ts(r: BrokerResult) -> float:
        if r.published_at is None:
            return float("-inf")
        p = r.published_at
        if p.tzinfo is None:
            from datetime import timezone as tz

            p = p.replace(tzinfo=tz.utc)
        return p.timestamp()

    def key(r: BrokerResult) -> tuple[int, bool, int, float, str]:
        cats = set(r.categories or [])
        if cats & {5000, 5070}:
            tier = 0
        elif 2000 in cats:
            tier = 1
        else:
            tier = 2
        s = r.seeders
        return (tier, s is None, -(int(s) if s is not None else 0), -_pub_ts(r), r.title.lower())

    return sorted(results, key=key)
