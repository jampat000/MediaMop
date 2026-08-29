"""Resolve a Refiner library, and everything a job needs from it.

This is the read path ADR-0014 asks for: the families stop asking "which scope is this?"
and start asking "which library is this?". Scope survives on the library row because it
still selects the cleanup behaviour — a movie release folder versus a whole season
folder — but it is no longer the key the module partitions on.

The fallback in :func:`resolve_library` is the compatibility hinge (ADR-0014 §5). Job
payloads written before the upgrade carry a ``media_scope`` and no ``library_id``, and
they are sitting in the queue at the moment the upgrade happens — which is exactly where
a half-finished remux lives. They resolve to the seeded library for their scope rather
than failing.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from mediamop.modules.refiner.refiner_library_model import (
    RefinerLibraryManagerLinkRow,
    RefinerLibraryRow,
    RefinerRuleSetRow,
)
from mediamop.modules.refiner.refiner_remux_rules import RefinerRulesConfig, normalize_audio_preference_mode


def _csv_values(raw: str | None) -> tuple[str, ...]:
    return tuple(part.strip() for part in (raw or "").split(",") if part.strip())


@dataclass(frozen=True, slots=True)
class LibraryAdmissionRules:
    """What this library will pick up, as data rather than module constants."""

    media_extensions: frozenset[str]
    exclude_markers: frozenset[str]
    include_patterns: tuple[str, ...]
    exclude_patterns: tuple[str, ...]
    min_file_size_mb: int
    max_file_size_mb: int
    min_file_age_seconds: int
    exclude_hidden: bool
    top_level_only: bool


def normalize_media_scope(raw: str | None) -> str:
    return "tv" if (raw or "movie").strip().lower() == "tv" else "movie"


def list_libraries(session: Session, *, enabled_only: bool = False) -> list[RefinerLibraryRow]:
    stmt = select(RefinerLibraryRow).order_by(RefinerLibraryRow.display_order, RefinerLibraryRow.id)
    if enabled_only:
        stmt = stmt.where(RefinerLibraryRow.enabled.is_(True))
    return list(session.scalars(stmt))


def get_library(session: Session, library_id: int) -> RefinerLibraryRow | None:
    return session.get(RefinerLibraryRow, library_id)


def seeded_library_for_scope(session: Session, media_scope: str) -> RefinerLibraryRow | None:
    """The oldest library covering a scope — what migration 0011 seeded."""

    scope = normalize_media_scope(media_scope)
    return session.scalars(
        select(RefinerLibraryRow)
        .where(RefinerLibraryRow.media_scope == scope)
        .order_by(RefinerLibraryRow.display_order, RefinerLibraryRow.id)
    ).first()


def resolve_library(
    session: Session,
    *,
    library_id: int | None = None,
    media_scope: str | None = None,
) -> RefinerLibraryRow | None:
    """A job's library: by id when the payload carries one, else the seeded one for its scope.

    A payload written before the upgrade has no ``library_id``. Failing it would strand
    queued work at exactly the moment an operator is least able to afford it.
    """

    if library_id is not None:
        found = get_library(session, library_id)
        if found is not None:
            return found
    return seeded_library_for_scope(session, media_scope or "movie")


def admission_rules_for(library: RefinerLibraryRow) -> LibraryAdmissionRules:
    return LibraryAdmissionRules(
        media_extensions=frozenset(e.lower() for e in _csv_values(library.media_extensions_csv)),
        exclude_markers=frozenset(m.lower() for m in _csv_values(library.exclude_markers_csv)),
        include_patterns=_csv_values(library.include_patterns_csv),
        exclude_patterns=_csv_values(library.exclude_patterns_csv),
        min_file_size_mb=max(0, int(library.min_file_size_mb)),
        max_file_size_mb=max(0, int(library.max_file_size_mb)),
        min_file_age_seconds=max(0, int(library.min_file_age_seconds)),
        exclude_hidden=bool(library.exclude_hidden),
        top_level_only=bool(library.top_level_only),
    )


def rules_config_for(session: Session, library: RefinerLibraryRow) -> RefinerRulesConfig | None:
    """The library's audio and subtitle rules, or ``None`` when it references no rule set."""

    if library.rule_set_id is None:
        return None
    rule_set = session.get(RefinerRuleSetRow, library.rule_set_id)
    if rule_set is None:
        return None
    return RefinerRulesConfig(
        primary_audio_lang=rule_set.primary_audio_lang,
        secondary_audio_lang=rule_set.secondary_audio_lang,
        tertiary_audio_lang=rule_set.tertiary_audio_lang,
        default_audio_slot=rule_set.default_audio_slot,  # type: ignore[arg-type]
        remove_commentary=bool(rule_set.remove_commentary),
        subtitle_mode=rule_set.subtitle_mode,  # type: ignore[arg-type]
        subtitle_langs=_csv_values(rule_set.subtitle_langs_csv),
        preserve_forced_subs=bool(rule_set.preserve_forced_subs),
        preserve_default_subs=bool(rule_set.preserve_default_subs),
        audio_preference_mode=normalize_audio_preference_mode(rule_set.audio_preference_mode),
        audio_sorters_json=rule_set.audio_sorters_json or "",
    )


def manager_connection_ids_for(session: Session, library: RefinerLibraryRow) -> tuple[int, ...]:
    """Connections this library names. Empty means the operator has linked none.

    ADR-0014 §4 retires the scope-to-kind inference: a library states which managers
    cover it, and Refiner asks all of them.
    """

    rows = session.scalars(
        select(RefinerLibraryManagerLinkRow.connection_id)
        .where(RefinerLibraryManagerLinkRow.library_id == library.id)
        .order_by(RefinerLibraryManagerLinkRow.connection_id)
    )
    return tuple(int(r) for r in rows)


def library_has_manager_links(session: Session, library: RefinerLibraryRow) -> bool:
    return bool(manager_connection_ids_for(session, library))
