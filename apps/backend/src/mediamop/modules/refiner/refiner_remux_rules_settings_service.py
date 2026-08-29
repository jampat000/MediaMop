"""The scope-shaped audio/subtitle surface, now backed by each library's rule set.

The ``refiner_remux_rules_settings`` singleton held ten fields and then the same ten
again with a ``tv_`` prefix. That was the shape ADR-0014 existed to end, and #333 moved
the real configuration onto ``refiner_rule_sets``. The table itself survived one release
as the rollback path and is gone now (#363).

The **shape** stays, because the Audio & subtitles tab reads and writes it and the
Refiner overview reads it. Rewriting those screens to prove a storage change is not a
trade worth making — the hazard was two stores holding the same values, and there is one
now. ``movie`` and ``tv`` here mean "the rule set of the library that covers that scope",
resolved exactly the way every other pre-library caller resolves it, so this view and the
work itself can never disagree about which library a scope means.
"""

from __future__ import annotations

from typing import Literal

from sqlalchemy.orm import Session

from mediamop.modules.refiner.refiner_library_model import RefinerRuleSetRow
from mediamop.modules.refiner.refiner_library_service import resolve_library
from mediamop.modules.refiner.refiner_remux_rules import (
    RefinerRulesConfig,
    default_refiner_remux_rules_config,
    normalize_audio_preference_mode,
)
from mediamop.modules.refiner.schemas_refiner_remux_rules_settings import (
    RefinerRemuxRulesScopeOut,
    RefinerRemuxRulesSettingsOut,
    RefinerRemuxRulesSettingsPutIn,
)

Scope = Literal["movie", "tv"]


def _rule_set_for_scope(db: Session, scope: str) -> RefinerRuleSetRow | None:
    """The rule set of the library covering this scope, or None when there is neither."""

    library = resolve_library(db, media_scope="tv" if scope == "tv" else "movie")
    if library is None or library.rule_set_id is None:
        return None
    return db.get(RefinerRuleSetRow, library.rule_set_id)


def _ensure_rule_set_for_scope(db: Session, scope: str) -> RefinerRuleSetRow:
    """The rule set for this scope, created and linked if the library has none.

    A library without a rule set is a library nothing can configure, so a save creates
    one rather than refusing — but it is linked to that library only, never shared with
    the other scope, because two scopes sharing one rule set by accident is how a TV
    change silently rewrites the Movies rules.
    """

    wanted: Scope = "tv" if scope == "tv" else "movie"
    library = resolve_library(db, media_scope=wanted)
    if library is None:
        msg = (
            f"No Refiner library covers {'TV' if wanted == 'tv' else 'Movies'}, so there is nowhere to save "
            "these rules. Add one on the Refiner Libraries settings page."
        )
        raise ValueError(msg)
    existing = db.get(RefinerRuleSetRow, library.rule_set_id) if library.rule_set_id is not None else None
    if existing is not None:
        return existing

    defaults = default_refiner_remux_rules_config()
    created = RefinerRuleSetRow(
        name=_unique_rule_set_name(db, f"{library.name} rules"),
        primary_audio_lang=defaults.primary_audio_lang,
        secondary_audio_lang=defaults.secondary_audio_lang,
        tertiary_audio_lang=defaults.tertiary_audio_lang,
        default_audio_slot=defaults.default_audio_slot,
        remove_commentary=defaults.remove_commentary,
        subtitle_mode=defaults.subtitle_mode,
        subtitle_langs_csv=",".join(defaults.subtitle_langs),
        preserve_forced_subs=defaults.preserve_forced_subs,
        preserve_default_subs=defaults.preserve_default_subs,
        audio_preference_mode=defaults.audio_preference_mode,
    )
    db.add(created)
    db.flush()
    library.rule_set_id = created.id
    db.flush()
    return created


def _unique_rule_set_name(db: Session, wanted: str) -> str:
    from sqlalchemy import select

    taken = set(db.scalars(select(RefinerRuleSetRow.name)))
    if wanted not in taken:
        return wanted
    for suffix in range(2, 100):
        candidate = f"{wanted} {suffix}"
        if candidate not in taken:
            return candidate
    return f"{wanted} {len(taken) + 1}"


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


def _scope_out(row: RefinerRuleSetRow | None) -> RefinerRemuxRulesScopeOut:
    config = rule_set_to_rules_config(row)
    return RefinerRemuxRulesScopeOut(
        primary_audio_lang=config.primary_audio_lang,
        secondary_audio_lang=config.secondary_audio_lang,
        tertiary_audio_lang=config.tertiary_audio_lang,
        default_audio_slot=config.default_audio_slot,
        remove_commentary=bool(config.remove_commentary),
        subtitle_mode=config.subtitle_mode,
        subtitle_langs_csv=",".join(config.subtitle_langs),
        preserve_forced_subs=bool(config.preserve_forced_subs),
        preserve_default_subs=bool(config.preserve_default_subs),
        audio_preference_mode=normalize_audio_preference_mode(config.audio_preference_mode),
    )


def build_refiner_remux_rules_settings_out(db: Session) -> RefinerRemuxRulesSettingsOut:
    """The two scopes, each read from the rule set of the library covering it."""

    movie_rules = _rule_set_for_scope(db, "movie")
    tv_rules = _rule_set_for_scope(db, "tv")
    newest = max(
        (row.updated_at for row in (movie_rules, tv_rules) if row is not None and row.updated_at is not None),
        default=None,
    )
    return RefinerRemuxRulesSettingsOut(
        movie=_scope_out(movie_rules),
        tv=_scope_out(tv_rules),
        updated_at=newest.isoformat() if newest else "",
    )


def apply_refiner_remux_rules_settings_put(db: Session, body: RefinerRemuxRulesSettingsPutIn) -> RefinerRuleSetRow:
    """Write one scope's rules onto the rule set of the library covering it."""

    if body.subtitle_mode == "keep_selected" and not (body.subtitle_langs_csv or "").strip():
        raise ValueError("When keeping subtitles, set at least one language in subtitle_langs_csv.")

    row = _ensure_rule_set_for_scope(db, body.media_scope)
    row.primary_audio_lang = body.primary_audio_lang.strip() or "eng"
    row.secondary_audio_lang = body.secondary_audio_lang.strip()
    row.tertiary_audio_lang = body.tertiary_audio_lang.strip()
    row.default_audio_slot = body.default_audio_slot
    row.remove_commentary = bool(body.remove_commentary)
    row.subtitle_mode = body.subtitle_mode
    row.subtitle_langs_csv = body.subtitle_langs_csv.strip()
    row.preserve_forced_subs = bool(body.preserve_forced_subs)
    row.preserve_default_subs = bool(body.preserve_default_subs)
    row.audio_preference_mode = body.audio_preference_mode
    db.flush()
    return row
