"""GET/PUT ``/api/v1/refiner/remux-rules-settings`` — operator remux planning defaults."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class RefinerRemuxRulesScopeOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    primary_audio_lang: str
    secondary_audio_lang: str
    tertiary_audio_lang: str
    default_audio_slot: Literal["primary", "secondary"]
    remove_commentary: bool
    subtitle_mode: Literal["remove_all", "keep_selected"]
    subtitle_langs_csv: str = Field(
        ...,
        description="Comma-separated ISO-style language tags used when subtitle_mode is keep_selected.",
    )
    preserve_forced_subs: bool
    preserve_default_subs: bool
    audio_preference_mode: Literal[
        "preferred_langs_quality",
        "preferred_langs_strict",
        "quality_all_languages",
    ]


class RefinerRemuxRulesSettingsOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    movie: RefinerRemuxRulesScopeOut
    tv: RefinerRemuxRulesScopeOut
    updated_at: str


class RefinerRemuxRulesSettingsPutIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    csrf_token: str = Field(..., min_length=1)
    media_scope: Literal["movie", "tv"] = "movie"
    primary_audio_lang: str = Field(default="eng", max_length=24)
    secondary_audio_lang: str = Field(default="jpn", max_length=24)
    tertiary_audio_lang: str = Field(default="", max_length=24)
    default_audio_slot: Literal["primary", "secondary"] = "primary"
    remove_commentary: bool = True
    subtitle_mode: Literal["remove_all", "keep_selected"] = "remove_all"
    subtitle_langs_csv: str = Field(default="", max_length=512)
    preserve_forced_subs: bool = True
    preserve_default_subs: bool = True
    audio_preference_mode: Literal[
        "preferred_langs_quality",
        "preferred_langs_strict",
        "quality_all_languages",
    ] = "preferred_langs_quality"
