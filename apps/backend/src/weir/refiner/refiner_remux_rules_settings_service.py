"""The audio and subtitle rules in force for a library, read from its rule set.

The ``refiner_remux_rules_settings`` singleton (Movies fields, then the same again with a
``tv_`` prefix) was replaced by ``refiner_rule_sets`` in #333 and dropped in #363. Its
scope-shaped HTTP view was deleted in #460; what remains is the conversion from a stored rule
set to the config the planner takes, and the fallback a pass uses when its library names no
rule set.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from weir.refiner.refiner_library_model import RefinerRuleSetRow
from weir.refiner.refiner_library_service import resolve_library
from weir.refiner.refiner_remux_rules import (
    RefinerRulesConfig,
    default_refiner_remux_rules_config,
    normalize_audio_preference_mode,
)


def _rule_set_for_scope(db: Session, scope: str) -> RefinerRuleSetRow | None:
    """The rule set of the library covering this scope, or None when there is neither."""

    library = resolve_library(db, media_scope="tv" if scope == "tv" else "movie")
    if library is None or library.rule_set_id is None:
        return None
    return db.get(RefinerRuleSetRow, library.rule_set_id)


def _normalize_subtitle_mode(raw: str | None) -> str:
    """The planner's own reading of a stored subtitle mode.

    ``refiner_rule_sets.subtitle_mode`` carries a ``keep_all`` server default, which is
    not one of the two modes anything actually implements — the planner asks
    ``config.subtitle_mode == "remove_all"`` and treats everything else as keep-selected.
    Reproducing that here rather than rewriting stored values keeps behaviour identical:
    a row saying ``keep_all`` already behaved as keep-selected, and a migration flipping
    it to ``remove_all`` would start deleting subtitles nobody asked to delete.
    """

    return "remove_all" if (raw or "").strip().lower() == "remove_all" else "keep_selected"


def rule_set_to_rules_config(row: RefinerRuleSetRow | None) -> RefinerRulesConfig:
    """One rule set as the config the planner takes.

    A missing rule set yields the shipped defaults rather than raising: a pass with no
    configured rules should behave the way a fresh install does, not fail.
    """

    if row is None:
        return default_refiner_remux_rules_config()
    return RefinerRulesConfig(
        primary_audio_lang=row.primary_audio_lang,
        secondary_audio_lang=row.secondary_audio_lang,
        tertiary_audio_lang=row.tertiary_audio_lang,
        default_audio_slot=row.default_audio_slot,  # type: ignore[arg-type]
        remove_commentary=bool(row.remove_commentary),
        subtitle_mode=_normalize_subtitle_mode(row.subtitle_mode),  # type: ignore[arg-type]
        subtitle_langs=tuple(x.strip() for x in (row.subtitle_langs_csv or "").split(",") if x.strip()),
        preserve_forced_subs=bool(row.preserve_forced_subs),
        preserve_default_subs=bool(row.preserve_default_subs),
        audio_preference_mode=normalize_audio_preference_mode(row.audio_preference_mode),
        audio_sorters_json=row.audio_sorters_json or "",
    )


def load_refiner_remux_rules_config(db: Session, media_scope: str = "movie") -> RefinerRulesConfig:
    """The rules in force for one scope."""

    return rule_set_to_rules_config(_rule_set_for_scope(db, media_scope))
