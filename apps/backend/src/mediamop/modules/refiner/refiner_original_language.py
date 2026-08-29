"""Keeping the original-language audio instead of whatever the preference list says.

Refiner picks audio from a fixed preference list — typically ``eng`` then ``jpn``. That is
right for a library where the operator always wants the same language, and wrong for a
mixed-origin one: for a French film with English and French audio, an ``eng``-first
preference keeps **the dub**. Most people who care about audio quality want the original.

The five options mirror FileFlows' ``Keep Original Language``, and one of them matters more
than the rest:

``first_if_none`` is a **safety net, not a preference**. Refiner already guarantees it
never produces a file with no audio — ``plan_remux`` returns ``None`` rather than write
one — and nothing here may weaken that. So this module only ever *reorders* candidates; it
never removes the last one, and the caller's existing fallback still runs when it declines
to choose.

When no provider is configured, or it cannot answer, the preference list decides exactly as
before. The notes say which mechanism chose, because "why did it keep the dub" is
unanswerable otherwise.

This module imports from ``refiner_remux_rules`` and is called by the *pass*, not by the
rules module. Putting the call inside ``_select_audio_winner`` would make the rules module
depend on an external integration and create an import cycle; keeping it at the pass level
also keeps the never-no-audio guarantee where it already lives.
"""

from __future__ import annotations

from dataclasses import dataclass

from mediamop.integrations.metadata.provider_port import LookupResult
from mediamop.modules.refiner.refiner_remux_rules import normalize_lang

#: Providers report ISO 639-1 (``fr``); media files are usually tagged ISO 639-2 (``fre``),
#: and the bibliographic and terminological 639-2 variants disagree (``fre``/``fra``).
#: Without this the feature would look configured and silently never match, which is the
#: worst kind of not working.
#:
#: **Ordered tuples, not sets.** The first entry is the canonical form, and it has to be
#: deterministic — a set would pick between two equal-length codes by hash order, which
#: varies between processes, so the same file could be described differently on different
#: runs. The bibliographic form comes first because that is what media files are tagged
#: with, so the note shows an operator the code they recognise.
#:
#: Only languages that actually appear in media libraries are listed. An exhaustive table
#: would be a maintenance burden for codes nobody tags.
_LANGUAGE_GROUPS: tuple[tuple[str, ...], ...] = (
    ("eng", "en"),
    ("fre", "fr", "fra"),
    ("ger", "de", "deu"),
    ("spa", "es"),
    ("ita", "it"),
    ("jpn", "ja"),
    ("kor", "ko"),
    ("chi", "zh", "zho"),
    ("por", "pt"),
    ("rus", "ru"),
    ("dut", "nl", "nld"),
    ("swe", "sv"),
    ("dan", "da"),
    ("nor", "no"),
    ("fin", "fi"),
    ("pol", "pl"),
    ("cze", "cs", "ces"),
    ("hun", "hu"),
    ("tur", "tr"),
    ("ara", "ar"),
    ("heb", "he"),
    ("hin", "hi"),
    ("tha", "th"),
    ("ukr", "uk"),
    ("gre", "el", "ell"),
    ("rum", "ro", "ron"),
    ("ice", "is", "isl"),
)

#: Every alias, mapped to its group's first entry so a lookup is one dictionary hit.
_CANONICAL: dict[str, str] = {code: group[0] for group in _LANGUAGE_GROUPS for code in group}


def canonical_language(raw: str | None) -> str:
    """One form per language, whichever standard the caller happened to use.

    A code MediaMop does not know is returned as it is rather than dropped: an unlisted
    language should still match itself.
    """

    code = normalize_lang((raw or "").strip())
    return _CANONICAL.get(code, code)


@dataclass(frozen=True, slots=True)
class OriginalLanguageRules:
    """The five options, all off by default so nothing changes until an operator opts in."""

    enabled: bool = False
    #: Extra ISO 639-2 codes kept alongside the original.
    additional_languages: tuple[str, ...] = ()
    #: Keep only the first track of each kept language.
    keep_only_first: bool = True
    #: If nothing matches, keep the first track regardless. The safety net.
    first_if_none: bool = True
    #: A track with no language tag is treated as the original language.
    treat_empty_as_original: bool = False


@dataclass(frozen=True, slots=True)
class OriginalLanguageOutcome:
    """Which tracks to prefer, and the sentence explaining the choice."""

    #: Input indices in preference order. Empty means "this module declined to choose",
    #: and the caller's existing preference-list behaviour applies unchanged.
    preferred_indices: tuple[int, ...] = ()
    note: str = ""

    @property
    def chose(self) -> bool:
        return bool(self.preferred_indices)


def parse_additional_languages(csv: str | None) -> tuple[str, ...]:
    out: list[str] = []
    for raw in (csv or "").split(","):
        code = canonical_language(raw)
        if code and code not in out:
            out.append(code)
    return tuple(out)


def select_original_language_tracks(
    *,
    rules: OriginalLanguageRules,
    lookup: LookupResult,
    tracks: list[dict],
) -> OriginalLanguageOutcome:
    """Order audio tracks by the original language, or decline and say why.

    ``tracks`` are dicts carrying at least ``index`` and ``language``. Declining is a
    first-class outcome: it is what happens with no provider, no match, or an unreachable
    one, and it leaves the existing behaviour exactly as it was.
    """

    if not rules.enabled:
        return OriginalLanguageOutcome(note="")

    if not lookup.matched or lookup.metadata is None:
        return OriginalLanguageOutcome(
            note=(
                f"Original-language selection did not apply ({lookup.detail or lookup.status}), so the "
                "configured language preferences chose the track."
            )
        )

    original = canonical_language(lookup.metadata.original_language)
    if not original:
        return OriginalLanguageOutcome(
            note=(
                "The metadata provider matched this title but reported no original language, so the "
                "configured language preferences chose the track."
            )
        )

    wanted: list[str] = [original, *[code for code in rules.additional_languages if code != original]]

    # Bucket by language in file order, so "the first track of each kept language" means
    # the first one in the file rather than an arbitrary one.
    by_language: dict[str, list[dict]] = {}
    for track in tracks:
        code = canonical_language(str(track.get("language") or ""))
        if not code and rules.treat_empty_as_original:
            code = original
        by_language.setdefault(code, []).append(track)

    ordered: list[int] = []
    for code in wanted:
        candidates = by_language.get(code, [])
        chosen = candidates[:1] if rules.keep_only_first else candidates
        ordered.extend(int(t["index"]) for t in chosen)

    if ordered:
        kept = ", ".join(wanted)
        return OriginalLanguageOutcome(
            preferred_indices=tuple(ordered),
            note=(
                f"Kept audio in the original language ({original}"
                + (f", plus {', '.join(rules.additional_languages)}" if rules.additional_languages else "")
                + f") because the metadata provider identified it. Preferred languages: {kept}."
            ),
        )

    if rules.first_if_none and tracks:
        # The safety net. It reorders nothing — it simply declines in a way that says so,
        # leaving the caller's own fallback to pick, which is what guarantees the output
        # still has audio.
        return OriginalLanguageOutcome(
            note=(
                f"No audio track matched the original language ({original}), so MediaMop fell back to the "
                "configured language preferences to be sure the output still has audio."
            )
        )

    return OriginalLanguageOutcome(
        note=(
            f"No audio track matched the original language ({original}), so the configured language "
            "preferences chose the track."
        )
    )
