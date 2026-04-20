"""Unit tests for :mod:`mediamop.modules.broker.broker_result`."""

from __future__ import annotations

from datetime import datetime, timezone

from mediamop.modules.broker.broker_result import BrokerResult, deduplicate_results, sort_results


def _r(
    *,
    title: str = "t",
    url: str = "u",
    magnet: str | None = None,
    size: int = 0,
    seeders: int | None = None,
    leechers: int | None = None,
    protocol: str = "torrent",
    indexer_slug: str = "s",
    categories: list[int] | None = None,
    published_at: datetime | None = None,
    imdb_id: str | None = None,
    info_hash: str | None = None,
) -> BrokerResult:
    return BrokerResult(
        title=title,
        url=url,
        magnet=magnet,
        size=size,
        seeders=seeders,
        leechers=leechers,
        protocol=protocol,
        indexer_slug=indexer_slug,
        categories=categories or [2000],
        published_at=published_at,
        imdb_id=imdb_id,
        info_hash=info_hash,
    )


def test_deduplicate_by_info_hash_keeps_highest_seeders() -> None:
    a = _r(info_hash="aa", seeders=10, title="a")
    b = _r(info_hash="aa", seeders=50, title="b")
    out = deduplicate_results([a, b])
    assert len(out) == 1
    assert out[0].seeders == 50


def test_deduplicate_fallback_url_when_no_hash() -> None:
    a = _r(info_hash=None, url="https://same", seeders=5)
    b = _r(info_hash=None, url="https://same", seeders=20)
    out = deduplicate_results([a, b])
    assert len(out) == 1
    assert out[0].seeders == 20


def test_sort_results_seeders_then_pub() -> None:
    older = datetime(2020, 1, 1, tzinfo=timezone.utc)
    newer = datetime(2024, 1, 1, tzinfo=timezone.utc)
    rows = [
        _r(title="low", seeders=5, published_at=older),
        _r(title="high", seeders=100, published_at=older),
        _r(title="none", seeders=None, published_at=newer),
    ]
    out = sort_results(rows)
    assert out[0].title == "high"
    assert out[1].title == "low"
    assert out[2].title == "none"
