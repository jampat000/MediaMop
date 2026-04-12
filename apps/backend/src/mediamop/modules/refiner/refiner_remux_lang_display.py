"""Shared ISO-639-3 → English labels for Refiner UI (overview + activity)."""

from __future__ import annotations

from mediamop.modules.refiner.refiner_remux_rules import normalize_lang

STREAM_LANGUAGE_OPTIONS: list[tuple[str, str]] = [
    ("eng", "English"),
    ("jpn", "Japanese"),
    ("spa", "Spanish"),
    ("fre", "French"),
    ("deu", "German"),
    ("ita", "Italian"),
    ("por", "Portuguese"),
    ("rus", "Russian"),
    ("zho", "Chinese"),
    ("kor", "Korean"),
    ("hin", "Hindi"),
    ("ara", "Arabic"),
    ("pol", "Polish"),
    ("tur", "Turkish"),
    ("swe", "Swedish"),
    ("dan", "Danish"),
    ("fin", "Finnish"),
    ("nld", "Dutch"),
    ("nor", "Norwegian"),
    ("hun", "Hungarian"),
    ("ces", "Czech"),
    ("ell", "Greek"),
    ("heb", "Hebrew"),
    ("tha", "Thai"),
    ("vie", "Vietnamese"),
    ("ukr", "Ukrainian"),
    ("ron", "Romanian"),
    ("ind", "Indonesian"),
    ("msa", "Malay"),
    ("und", "Undetermined"),
]


def refiner_lang_display(code: str | None) -> str:
    c = normalize_lang(code or "")
    if not c:
        return "—"
    for k, lbl in STREAM_LANGUAGE_OPTIONS:
        if k == c:
            return lbl
    return c.upper()


def refiner_lang_display_or_blank(code: str | None) -> str:
    """Label for ordered lists; empty codes are dropped by callers."""
    c = normalize_lang(code or "")
    if not c:
        return ""
    for k, lbl in STREAM_LANGUAGE_OPTIONS:
        if k == c:
            return lbl
    return c.upper()
