"""HTTP: Broker federated search under ``/api/v1/broker/search``."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, HTTPException, Query
from starlette import status

from mediamop.api.deps import DbSessionDep
from mediamop.modules.broker.broker_result import BrokerResult
from mediamop.modules.broker.broker_schemas import BrokerResultOut
from mediamop.modules.broker.broker_search_service import federated_search, sort_tv_before_movies_for_mixed
from mediamop.platform.auth.authorization import RequireOperatorDep

router = APIRouter(tags=["broker-search"])


def _result_out(r: BrokerResult) -> BrokerResultOut:
    return BrokerResultOut(
        title=r.title,
        url=r.url,
        magnet=r.magnet,
        size=r.size,
        seeders=r.seeders,
        leechers=r.leechers,
        protocol=r.protocol,
        indexer_slug=r.indexer_slug,
        categories=list(r.categories),
        published_at=r.published_at,
        imdb_id=r.imdb_id,
        info_hash=r.info_hash,
    )


@router.get("/search", response_model=list[BrokerResultOut])
async def get_broker_search(
    _user: RequireOperatorDep,
    db: DbSessionDep,
    q: Annotated[str, Query(min_length=1)],
    media_type: Annotated[str, Query(alias="type")] = "all",
    indexers: Annotated[str, Query(description="Comma-separated indexer ids; empty = all enabled.")] = "",
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> list[BrokerResultOut]:
    t = (media_type or "all").strip().lower()
    if t not in ("all", "tv", "movie", "movies"):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="type must be one of: all, tv, movie.",
        )
    media = "movie" if t == "movies" else t
    ids: list[int] | None = None
    raw = (indexers or "").strip()
    if raw:
        try:
            ids = [int(x.strip()) for x in raw.split(",") if x.strip()]
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="indexers must be comma-separated integers.",
            ) from exc
        if not ids:
            return []
    rows = await federated_search(
        db,
        query=q,
        media_type=media,
        indexer_ids=ids,
        limit_per_indexer=limit,
        timeout_seconds=10.0,
        protocol_filter="all",
    )
    if media == "all":
        rows = sort_tv_before_movies_for_mixed(rows)
    return [_result_out(r) for r in rows]
