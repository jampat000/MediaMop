"""Media-manager queue row -> :class:`RefinerQueueRowView`, driven by a media-scope dialect.

A queue row differs by *what kind of library it describes*, not by which product sent
it. A movie row nests its entity under ``movie`` and identifies it with ``movieId``; an
episode row nests under ``series`` and uses ``seriesId``. Those are two shapes, not two
products, so the dialect is keyed by media scope and carries the neutral key names
alongside the older ones. A manager that serves both scopes needs no new code here —
its outbound dialect in :mod:`mediamop.platform.media_managers.manager_dialects` tags
each row with the scope it describes, and the right dialect reads it.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Literal

from mediamop.modules.refiner.domain import RefinerQueueRowView
from mediamop.modules.refiner.queue_row_plumbing import (
    blocking_suppressed_for_import_wait,
    first_int,
    first_str,
    nested_dict,
    path_matches_candidate,
    primary_queue_status,
)

MediaScope = Literal["movie", "tv"]

# Shared across every scope: a queue row is "upstream active" in the same states
# whatever produced it. Previously duplicated per vendor with identical contents.
_STATUSES_UPSTREAM_ACTIVE: frozenset[str] = frozenset(
    {
        "downloading",
        "queued",
        "paused",
        "delay",
        "downloadpending",
        "downloadclientunavailable",
        "warning",
    }
)


@dataclass(frozen=True)
class QueueDialect:
    """How to read the entity out of one queue row for a given media scope."""

    scope: MediaScope
    entity_keys: tuple[str, ...]
    entity_title_fields: tuple[str, ...]
    entity_id_fields: tuple[str, ...]
    active_statuses: frozenset[str] = _STATUSES_UPSTREAM_ACTIVE


MOVIE_QUEUE_DIALECT = QueueDialect(
    scope="movie",
    entity_keys=("movie", "media", "item"),
    entity_title_fields=("title", "originalTitle", "original_title"),
    entity_id_fields=("movieId", "movie_id", "entityId", "entity_id"),
)

TV_QUEUE_DIALECT = QueueDialect(
    scope="tv",
    entity_keys=("series", "show", "media", "item"),
    entity_title_fields=("title", "sortTitle", "sort_title"),
    entity_id_fields=("seriesId", "series_id", "entityId", "entity_id"),
)

_DIALECTS_BY_SCOPE: dict[str, QueueDialect] = {
    "movie": MOVIE_QUEUE_DIALECT,
    "movies": MOVIE_QUEUE_DIALECT,
    "tv": TV_QUEUE_DIALECT,
    "series": TV_QUEUE_DIALECT,
}


def queue_dialect_for_scope(scope: str) -> QueueDialect:
    """Resolve a dialect from a media-scope string, accepting the common spellings."""

    try:
        return _DIALECTS_BY_SCOPE[(scope or "").strip().lower()]
    except KeyError:
        raise ValueError(f"Unknown media scope for queue dialect: {scope!r}") from None


def _queue_title_and_year(
    row: Mapping[str, Any],
    dialect: QueueDialect,
) -> tuple[str | None, int | None]:
    for key in dialect.entity_keys:
        entity = nested_dict(row, key)
        if entity is None:
            continue
        title = first_str(entity, *dialect.entity_title_fields)
        year = first_int(entity, "year")
        if title is not None:
            return title, year
    # Year only ever comes from the nested entity, matching the previous per-vendor
    # behaviour: a top-level year on the row is not trusted to describe the entity.
    return first_str(row, "title", "name"), None


def _applies_to_file(
    row: Mapping[str, Any],
    dialect: QueueDialect,
    *,
    candidate_path: str | None,
    candidate_entity_id: int | None,
) -> bool:
    if path_matches_candidate(row, candidate_path):
        return True
    if candidate_entity_id is None:
        return False
    row_id = first_int(row, *dialect.entity_id_fields)
    return row_id is not None and row_id == candidate_entity_id


def map_queue_row_to_refiner_view(
    row: Mapping[str, Any],
    dialect: QueueDialect,
    *,
    candidate_path: str | None = None,
    candidate_entity_id: int | None = None,
) -> RefinerQueueRowView:
    """Map one media-manager queue row to the Refiner domain row view.

    **applies_to_file** — ``outputPath`` matches ``candidate_path``, and/or the row's
    scope id field matches ``candidate_entity_id``.

    **queue_title** / **queue_year** — from the nested entity named by the dialect when
    present, else the row's top-level ``title`` / ``name`` (year only from the entity).
    """

    status = primary_queue_status(row)
    is_import_pending = status == "importpending"
    is_upstream_active = status in dialect.active_statuses and not is_import_pending
    title, year = _queue_title_and_year(row, dialect)
    return RefinerQueueRowView(
        applies_to_file=_applies_to_file(
            row,
            dialect,
            candidate_path=candidate_path,
            candidate_entity_id=candidate_entity_id,
        ),
        is_upstream_active=is_upstream_active,
        is_import_pending=is_import_pending,
        blocking_suppressed_for_import_wait=blocking_suppressed_for_import_wait(row),
        queue_title=title,
        queue_year=year,
    )
