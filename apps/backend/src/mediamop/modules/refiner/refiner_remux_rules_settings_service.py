"""Singleton remux rules row — load/save and map to :class:`RefinerRulesConfig`."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from mediamop.modules.refiner.refiner_remux_rules import (
    RefinerRulesConfig,
    default_refiner_remux_rules_config,
    normalize_audio_preference_mode,
    parse_subtitle_langs_csv,
)
from mediamop.modules.refiner.refiner_remux_rules_settings_model import RefinerRemuxRulesSettingsRow
from mediamop.modules.refiner.schemas_refiner_remux_rules_settings import (
    RefinerRemuxRulesScopeOut,
    RefinerRemuxRulesSettingsOut,
    RefinerRemuxRulesSettingsPutIn,
)


def ensure_refiner_remux_rules_settings_row(db: Session) -> RefinerRemuxRulesSettingsRow:
    row = db.scalars(select(RefinerRemuxRulesSettingsRow).where(RefinerRemuxRulesSettingsRow.id == 1)).one_or_none()
    if row is None:
        d = default_refiner_remux_rules_config()
        langs = ",".join(d.subtitle_langs)
        row = RefinerRemuxRulesSettingsRow(
            id=1,
            primary_audio_lang=d.primary_audio_lang,
            secondary_audio_lang=d.secondary_audio_lang,
            tertiary_audio_lang=d.tertiary_audio_lang,
            default_audio_slot=d.default_audio_slot,
            remove_commentary=1 if d.remove_commentary else 0,
            subtitle_mode=d.subtitle_mode,
            subtitle_langs_csv=langs,
            preserve_forced_subs=1 if d.preserve_forced_subs else 0,
            preserve_default_subs=1 if d.preserve_default_subs else 0,
            audio_preference_mode=d.audio_preference_mode,
            tv_primary_audio_lang=d.primary_audio_lang,
            tv_secondary_audio_lang=d.secondary_audio_lang,
            tv_tertiary_audio_lang=d.tertiary_audio_lang,
            tv_default_audio_slot=d.default_audio_slot,
            tv_remove_commentary=1 if d.remove_commentary else 0,
            tv_subtitle_mode=d.subtitle_mode,
            tv_subtitle_langs_csv=langs,
            tv_preserve_forced_subs=1 if d.preserve_forced_subs else 0,
            tv_preserve_default_subs=1 if d.preserve_default_subs else 0,
            tv_audio_preference_mode=d.audio_preference_mode,
        )
        db.add(row)
        db.flush()
    return row


def row_to_rules_config(row: RefinerRemuxRulesSettingsRow, media_scope: str = "movie") -> RefinerRulesConfig:
    movie = media_scope != "tv"
    primary = row.primary_audio_lang if movie else row.tv_primary_audio_lang
    secondary = row.secondary_audio_lang if movie else row.tv_secondary_audio_lang
    tertiary = row.tertiary_audio_lang if movie else row.tv_tertiary_audio_lang
    default_slot = row.default_audio_slot if movie else row.tv_default_audio_slot
    remove_commentary = row.remove_commentary if movie else row.tv_remove_commentary
    subtitle_mode = row.subtitle_mode if movie else row.tv_subtitle_mode
    subtitle_langs_csv = row.subtitle_langs_csv if movie else row.tv_subtitle_langs_csv
    preserve_forced_subs = row.preserve_forced_subs if movie else row.tv_preserve_forced_subs
    preserve_default_subs = row.preserve_default_subs if movie else row.tv_preserve_default_subs
    audio_preference_mode = row.audio_preference_mode if movie else row.tv_audio_preference_mode

    return RefinerRulesConfig(
        primary_audio_lang=(primary or "").strip() or "eng",
        secondary_audio_lang=(secondary or "").strip(),
        tertiary_audio_lang=(tertiary or "").strip(),
        default_audio_slot=default_slot if default_slot in ("primary", "secondary") else "primary",  # type: ignore[arg-type]
        remove_commentary=bool(remove_commentary),
        subtitle_mode=subtitle_mode if subtitle_mode in ("remove_all", "keep_selected") else "remove_all",  # type: ignore[arg-type]
        subtitle_langs=parse_subtitle_langs_csv(subtitle_langs_csv or ""),
        preserve_forced_subs=bool(preserve_forced_subs),
        preserve_default_subs=bool(preserve_default_subs),
        audio_preference_mode=normalize_audio_preference_mode(audio_preference_mode),
    )


def load_refiner_remux_rules_config(db: Session, media_scope: str = "movie") -> RefinerRulesConfig:
    row = ensure_refiner_remux_rules_settings_row(db)
    return row_to_rules_config(row, media_scope=media_scope)


def _scope_out(
    *,
    primary_audio_lang: str,
    secondary_audio_lang: str,
    tertiary_audio_lang: str,
    default_audio_slot: str,
    remove_commentary: int,
    subtitle_mode: str,
    subtitle_langs_csv: str,
    preserve_forced_subs: int,
    preserve_default_subs: int,
    audio_preference_mode: str,
) -> RefinerRemuxRulesScopeOut:
    return RefinerRemuxRulesScopeOut(
        primary_audio_lang=primary_audio_lang,
        secondary_audio_lang=secondary_audio_lang,
        tertiary_audio_lang=tertiary_audio_lang,
        default_audio_slot=default_audio_slot,  # type: ignore[arg-type]
        remove_commentary=bool(remove_commentary),
        subtitle_mode=subtitle_mode,  # type: ignore[arg-type]
        subtitle_langs_csv=subtitle_langs_csv or "",
        preserve_forced_subs=bool(preserve_forced_subs),
        preserve_default_subs=bool(preserve_default_subs),
        audio_preference_mode=normalize_audio_preference_mode(audio_preference_mode),  # type: ignore[arg-type]
    )


def build_refiner_remux_rules_settings_out(row: RefinerRemuxRulesSettingsRow) -> RefinerRemuxRulesSettingsOut:
    return RefinerRemuxRulesSettingsOut(
        movie=_scope_out(
            primary_audio_lang=row.primary_audio_lang,
            secondary_audio_lang=row.secondary_audio_lang,
            tertiary_audio_lang=row.tertiary_audio_lang,
            default_audio_slot=row.default_audio_slot,
            remove_commentary=row.remove_commentary,
            subtitle_mode=row.subtitle_mode,
            subtitle_langs_csv=row.subtitle_langs_csv,
            preserve_forced_subs=row.preserve_forced_subs,
            preserve_default_subs=row.preserve_default_subs,
            audio_preference_mode=row.audio_preference_mode,
        ),
        tv=_scope_out(
            primary_audio_lang=row.tv_primary_audio_lang,
            secondary_audio_lang=row.tv_secondary_audio_lang,
            tertiary_audio_lang=row.tv_tertiary_audio_lang,
            default_audio_slot=row.tv_default_audio_slot,
            remove_commentary=row.tv_remove_commentary,
            subtitle_mode=row.tv_subtitle_mode,
            subtitle_langs_csv=row.tv_subtitle_langs_csv,
            preserve_forced_subs=row.tv_preserve_forced_subs,
            preserve_default_subs=row.tv_preserve_default_subs,
            audio_preference_mode=row.tv_audio_preference_mode,
        ),
        updated_at=row.updated_at.isoformat() if row.updated_at else "",
    )


def apply_refiner_remux_rules_settings_put(db: Session, body: RefinerRemuxRulesSettingsPutIn) -> RefinerRemuxRulesSettingsRow:
    row = ensure_refiner_remux_rules_settings_row(db)
    if body.subtitle_mode == "keep_selected" and not (body.subtitle_langs_csv or "").strip():
        raise ValueError("When keeping subtitles, set at least one language in subtitle_langs_csv.")

    if body.media_scope == "tv":
        row.tv_primary_audio_lang = body.primary_audio_lang.strip() or "eng"
        row.tv_secondary_audio_lang = body.secondary_audio_lang.strip()
        row.tv_tertiary_audio_lang = body.tertiary_audio_lang.strip()
        row.tv_default_audio_slot = body.default_audio_slot
        row.tv_remove_commentary = 1 if body.remove_commentary else 0
        row.tv_subtitle_mode = body.subtitle_mode
        row.tv_subtitle_langs_csv = body.subtitle_langs_csv.strip()
        row.tv_preserve_forced_subs = 1 if body.preserve_forced_subs else 0
        row.tv_preserve_default_subs = 1 if body.preserve_default_subs else 0
        row.tv_audio_preference_mode = body.audio_preference_mode
    else:
        row.primary_audio_lang = body.primary_audio_lang.strip() or "eng"
        row.secondary_audio_lang = body.secondary_audio_lang.strip()
        row.tertiary_audio_lang = body.tertiary_audio_lang.strip()
        row.default_audio_slot = body.default_audio_slot
        row.remove_commentary = 1 if body.remove_commentary else 0
        row.subtitle_mode = body.subtitle_mode
        row.subtitle_langs_csv = body.subtitle_langs_csv.strip()
        row.preserve_forced_subs = 1 if body.preserve_forced_subs else 0
        row.preserve_default_subs = 1 if body.preserve_default_subs else 0
        row.audio_preference_mode = body.audio_preference_mode
    db.flush()
    return row
