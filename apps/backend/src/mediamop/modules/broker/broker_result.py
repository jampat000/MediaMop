"""Unified search result row for Broker federated search and proxies."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone


@dataclass(slots=True)
class BrokerResult:
    title: str
    url: str
    magnet: str | None
    size: int
    seeders: int | None
    leechers: int | None
    protocol: str
    indexer_slug: str
    categories: list[int]
    published_at: datetime | None
    imdb_id: str | None
    info_hash: str | None


def _seeders_key(r: BrokerResult) -> int:
    return int(r.seeders) if r.seeders is not None else -1


def _pub_ts(r: BrokerResult) -> float:
    if r.published_at is None:
        return float("-inf")
    p = r.published_at
    if p.tzinfo is None:
        p = p.replace(tzinfo=timezone.utc)
    return p.timestamp()


def deduplicate_results(results: list[BrokerResult]) -> list[BrokerResult]:
    """Remove duplicates by info_hash (torrents) or url (usenet/fallback).

    Keeps the result with the highest seeder count when duplicates exist.
    """

    best: dict[str, BrokerResult] = {}
    for r in results:
        key = (r.info_hash or "").strip().lower() if (r.info_hash or "").strip() else ""
        if not key:
            key = f"url:{r.url}"
        cur = best.get(key)
        if cur is None or _seeders_key(r) > _seeders_key(cur):
            best[key] = r
    return list(best.values())


def sort_results(results: list[BrokerResult]) -> list[BrokerResult]:
    """Sort by seeders desc (None last), then published_at desc (None last)."""

    def sort_key(r: BrokerResult) -> tuple[bool, int, bool, float, str]:
        s = r.seeders
        s_none = s is None
        s_val = -(int(s) if s is not None else 0)
        p = r.published_at
        p_none = p is None
        p_val = -_pub_ts(r) if p is not None else 0.0
        return (s_none, s_val, p_none, p_val, r.title.lower())

    return sorted(results, key=sort_key)
