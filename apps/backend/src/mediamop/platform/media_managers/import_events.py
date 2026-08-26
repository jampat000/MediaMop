"""One inbound event shape for every media manager, plus the dialects that produce it.

A media manager tells MediaMop "here is a file, do your thing with it". Radarr and
Sonarr say that in their own JSON, Deluno says it in its hand-off payload, and anything
else can post the native shape. Only the unwrapping differs, so the unwrapping is the
only thing that is per-manager: each dialect turns one raw body into a
:class:`MediaManagerImportEvent`, and everything downstream reads that.

Adding a manager means adding a dialect here, not a route, a job kind, or a module.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any, Literal

MediaScope = Literal["movie", "tv"]
EventKind = Literal["imported", "handoff"]

# Subber's stored payloads have always spelled the movie scope "movies"; the queue
# dialects use "movie". Convert at the boundary rather than teaching one of them both.
_SUBBER_SCOPE = {"movie": "movies", "tv": "tv"}


@dataclass(frozen=True, slots=True)
class MediaManagerImportEvent:
    """A file a media manager wants MediaMop to act on.

    ``event_kind`` separates the two reasons a manager gets in touch. ``imported`` is
    "I have finished with this file and it is in the library now" — Subber's cue to look
    for subtitles. ``handoff`` is "I have not finished; clean this up and tell me when
    you are done" — Refiner's cue, and the only kind that carries a callback.
    """

    source_key: str
    event_kind: EventKind
    media_scope: MediaScope
    file_path: str
    title: str | None = None
    year: int | None = None
    show_title: str | None = None
    season_number: int | None = None
    episode_number: int | None = None
    episode_title: str | None = None
    source_entity_id: int | None = None
    handoff_id: str | None = None
    callback_path: str | None = None
    release_name: str | None = None

    def to_subber_job_payload(self) -> dict[str, Any]:
        """Render the payload Subber's webhook-import job handler already expects."""

        return {
            "file_path": self.file_path,
            "media_scope": _SUBBER_SCOPE[self.media_scope],
            "title": self.title,
            "year": self.year,
            "show_title": self.show_title,
            "season_number": self.season_number,
            "episode_number": self.episode_number,
            "episode_title": self.episode_title,
            # Kept under the historical key names so stored rows stay readable across
            # the upgrade; both are simply "the id the source used for this entity".
            "sonarr_episode_id": self.source_entity_id if self.media_scope == "tv" else None,
            "radarr_movie_id": self.source_entity_id if self.media_scope == "movie" else None,
        }


def _text(value: Any) -> str | None:
    return value.strip() or None if isinstance(value, str) else None


def _whole_number(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return None


def _mapping(body: Mapping[str, Any], key: str) -> Mapping[str, Any] | None:
    value = body.get(key)
    return value if isinstance(value, Mapping) else None


def _normalize_sonarr(body: Mapping[str, Any]) -> MediaManagerImportEvent | None:
    if _text(body.get("eventType")) != "Download":
        return None
    episodes = body.get("episodes")
    if not isinstance(episodes, list) or not episodes:
        return None
    episode = episodes[0]
    if not isinstance(episode, Mapping):
        return None
    episode_file = _mapping(body, "episodeFile")
    path = _text(episode_file.get("path")) if episode_file else None
    if path is None:
        return None
    series = _mapping(body, "series")
    series_title = _text(series.get("title")) if series else None
    return MediaManagerImportEvent(
        source_key="sonarr",
        event_kind="imported",
        media_scope="tv",
        file_path=path,
        title=series_title,
        show_title=series_title,
        season_number=_whole_number(episode.get("seasonNumber")),
        episode_number=_whole_number(episode.get("episodeNumber")),
        episode_title=_text(episode.get("title")),
        source_entity_id=_whole_number(episode.get("id")),
    )


def _normalize_radarr(body: Mapping[str, Any]) -> MediaManagerImportEvent | None:
    if _text(body.get("eventType")) != "Download":
        return None
    movie = _mapping(body, "movie")
    if movie is None:
        return None
    movie_file = _mapping(body, "movieFile")
    path = _text(movie_file.get("path")) if movie_file else None
    if path is None:
        return None
    return MediaManagerImportEvent(
        source_key="radarr",
        event_kind="imported",
        media_scope="movie",
        file_path=path,
        title=_text(movie.get("title")),
        year=_whole_number(movie.get("year")),
        source_entity_id=_whole_number(movie.get("id")),
    )


def _scope_from_media_type(raw: Any) -> MediaScope | None:
    value = (_text(raw) or "").lower()
    if value in {"movie", "movies", "film"}:
        return "movie"
    if value in {"tv", "series", "show", "episode"}:
        return "tv"
    return None


def _normalize_deluno(body: Mapping[str, Any]) -> MediaManagerImportEvent | None:
    """Deluno's processor hand-off: clean this path and call back when done."""

    if _text(body.get("eventType")) != "deluno.processor-handoff":
        return None
    path = _text(body.get("sourcePath"))
    scope = _scope_from_media_type(body.get("mediaType"))
    if path is None or scope is None:
        return None
    release_name = _text(body.get("releaseName"))
    return MediaManagerImportEvent(
        source_key="deluno",
        event_kind="handoff",
        media_scope=scope,
        file_path=path,
        title=release_name,
        release_name=release_name,
        handoff_id=_text(body.get("handoffId")),
        callback_path=_text(body.get("callbackPath")),
    )


def _normalize_native(body: Mapping[str, Any]) -> MediaManagerImportEvent | None:
    """MediaMop's own shape, for a manager with no dialect of its own.

    Documented contract: ``event`` is ``imported`` or ``handoff``, ``filePath`` and
    ``mediaScope`` are required, everything else is optional.
    """

    kind = (_text(body.get("event")) or "imported").lower()
    if kind not in {"imported", "handoff"}:
        return None
    path = _text(body.get("filePath")) or _text(body.get("file_path"))
    scope = _scope_from_media_type(body.get("mediaScope") or body.get("media_scope"))
    if path is None or scope is None:
        return None
    return MediaManagerImportEvent(
        source_key="native",
        event_kind="imported" if kind == "imported" else "handoff",
        media_scope=scope,
        file_path=path,
        title=_text(body.get("title")),
        year=_whole_number(body.get("year")),
        show_title=_text(body.get("showTitle") or body.get("show_title")),
        season_number=_whole_number(body.get("seasonNumber") or body.get("season_number")),
        episode_number=_whole_number(body.get("episodeNumber") or body.get("episode_number")),
        episode_title=_text(body.get("episodeTitle") or body.get("episode_title")),
        source_entity_id=_whole_number(body.get("entityId") or body.get("entity_id")),
        handoff_id=_text(body.get("handoffId") or body.get("handoff_id")),
        callback_path=_text(body.get("callbackPath") or body.get("callback_path")),
        release_name=_text(body.get("releaseName") or body.get("release_name")),
    )


@dataclass(frozen=True, slots=True)
class MediaManagerDialect:
    """How one manager phrases an inbound event."""

    key: str
    display_name: str
    normalize: Callable[[Mapping[str, Any]], MediaManagerImportEvent | None]


MEDIA_MANAGER_DIALECTS: dict[str, MediaManagerDialect] = {
    dialect.key: dialect
    for dialect in (
        MediaManagerDialect("radarr", "Radarr", _normalize_radarr),
        MediaManagerDialect("sonarr", "Sonarr", _normalize_sonarr),
        MediaManagerDialect("deluno", "Deluno", _normalize_deluno),
        MediaManagerDialect("native", "Generic (MediaMop native payload)", _normalize_native),
    )
}


def dialect_for_source(source_key: str) -> MediaManagerDialect | None:
    return MEDIA_MANAGER_DIALECTS.get((source_key or "").strip().lower())


def known_source_keys() -> tuple[str, ...]:
    return tuple(sorted(MEDIA_MANAGER_DIALECTS))
