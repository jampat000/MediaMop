"""An ordered, editable list of sorters replaces a fixed tuple in source.

Refiner ranked audio tracks with a hardcoded six-key tuple. An operator could pick one of
three policies and three language tiers, but the ranking *inside* a tier was fixed:
wanting "prefer DTS-HD over TrueHD", or "prefer 5.1 over 7.1", or "prefer the track whose
title does not say Descriptive" meant a code change.

A sorter list is the same idea as the tuple, with the order and the contents moved into
data. Each entry contributes one component of the sort key, in the order the operator put
them in, and the track index is always the final tiebreak so the result is a total order
however the list is configured.

Two kinds of entry, distinguished by whether a ``value`` is given:

**A match test** — ``language = eng``, ``channels >= 5.1``, ``title != commentary``.
Tracks that match sort ahead of tracks that do not. This is what most sorters are, and it
reads the way an operator thinks: "English first, then 5.1 or better".

**A natural ordering** — ``channels`` with no value. Sorts by the field itself, best
first, where "best" means more channels, more bitrate, better codec. ``reversed`` flips
it, because "prefer the *smallest* track that still qualifies" is a real preference.

The seeded default reproduces the old tuple exactly, so nothing changes on upgrade until
someone edits the list. There is a test that asserts precisely that against the original
implementation rather than against a description of it.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Literal

#: The vocabulary. The first seven are FileFlows' own; ``commentary`` is added because
#: Refiner detects commentary from more than a title substring, and a seeded default that
#: could not express the existing demotion would not be a faithful seed.
SorterField = Literal[
    "bitrate",
    "channels",
    "codec",
    "language",
    "title",
    "default",
    "forced",
    "commentary",
]

SORTER_FIELDS: tuple[str, ...] = (
    "bitrate",
    "channels",
    "codec",
    "language",
    "title",
    "default",
    "forced",
    "commentary",
)

#: Fields where a larger number is better, so the natural order is descending.
_LARGER_IS_BETTER: frozenset[str] = frozenset({"bitrate", "channels"})

_COMPARISON_RE = re.compile(r"^\s*(>=|<=|!=|>|<|=)?\s*(.+?)\s*$")


class TrackSorterError(ValueError):
    """The sorter list is not usable."""


@dataclass(frozen=True, slots=True)
class TrackSorter:
    """One entry in the ordered list."""

    field: str
    #: ``None`` means "sort by this field naturally". Anything else is a match test.
    value: str | None = None
    #: Flips the direction, for both kinds of entry.
    reversed: bool = False

    def describe(self) -> str:
        """A phrase for the selection notes, written the way the operator configured it."""

        if self.value is None:
            direction = "lowest first" if self.reversed != (self.field in _LARGER_IS_BETTER) else "highest first"
            if self.field in {"default", "forced", "commentary"}:
                direction = "last" if self.reversed else "first"
                return f"{self.field} {direction}"
            if self.field in {"codec", "language", "title"}:
                return f"{self.field} order"
            return f"{self.field} {direction}"
        prefix = "not " if self.reversed else ""
        return f"{prefix}{self.field} {self.value}"


def _parse_channels(text: str) -> float | None:
    """``5.1`` means six channels, and operators write it that way.

    Accepting only a bare integer would make the most common expression an operator
    reaches for — ``>=5.1`` — silently fail to match anything.
    """

    raw = text.strip().lower()
    if raw in {"mono", "1.0"}:
        return 1.0
    if raw in {"stereo", "2.0"}:
        return 2.0
    if "." in raw:
        try:
            main, lfe = raw.split(".", 1)
            return float(int(main) + int(lfe))
        except (ValueError, TypeError):
            return None
    try:
        return float(int(raw))
    except (ValueError, TypeError):
        return None


def _compare(actual: Any, operator: str, expected: str, *, field: str) -> bool:
    if field == "channels":
        wanted = _parse_channels(expected)
        try:
            have = float(actual or 0)
        except (TypeError, ValueError):
            have = 0.0
        if wanted is None:
            return False
        return _numeric_compare(have, operator, wanted)

    if field == "bitrate":
        try:
            wanted_num = float(expected.strip().lower().rstrip("k").replace("_", ""))
        except (TypeError, ValueError):
            return False
        if expected.strip().lower().endswith("k"):
            wanted_num *= 1000
        try:
            have_num = float(actual or 0)
        except (TypeError, ValueError):
            have_num = 0.0
        return _numeric_compare(have_num, operator, wanted_num)

    if field in {"default", "forced", "commentary"}:
        wanted_bool = expected.strip().lower() in {"1", "true", "yes", "on"}
        have_bool = bool(actual)
        return have_bool != wanted_bool if operator == "!=" else have_bool == wanted_bool

    # Text fields compare case-insensitively, and ``title`` is a containment test because
    # "the title mentions commentary" is the useful question, not "the title equals it".
    have_text = str(actual or "").strip().lower()
    want_text = expected.strip().lower()
    matched = want_text in have_text if field == "title" else have_text == want_text
    return (not matched) if operator == "!=" else matched


def _numeric_compare(have: float, operator: str, wanted: float) -> bool:
    if operator == ">=":
        return have >= wanted
    if operator == "<=":
        return have <= wanted
    if operator == ">":
        return have > wanted
    if operator == "<":
        return have < wanted
    if operator == "!=":
        return have != wanted
    return have == wanted


def _split_expression(value: str) -> tuple[str, str]:
    match = _COMPARISON_RE.match(value)
    if match is None:
        return "=", value.strip()
    return (match.group(1) or "="), match.group(2)


def sorter_key_component(sorter: TrackSorter, track: dict[str, Any]) -> tuple[int, ...]:
    """One sorter's contribution to the sort key. Lower sorts first."""

    actual = track.get(sorter.field)

    if sorter.value is not None:
        operator, expected = _split_expression(sorter.value)
        matched = _compare(actual, operator, expected, field=sorter.field)
        if sorter.reversed:
            matched = not matched
        return (0 if matched else 1,)

    if sorter.field in {"default", "forced", "commentary"}:
        flag = 1 if actual else 0
        # ``commentary`` naturally sorts commentary *last*: it is a demotion, which is
        # what the fixed ranking did and what anyone adding it would expect.
        if sorter.field == "commentary":
            return (flag if not sorter.reversed else 1 - flag,)
        return (1 - flag if not sorter.reversed else flag,)

    if sorter.field in _LARGER_IS_BETTER:
        try:
            number = int(actual or 0)
        except (TypeError, ValueError):
            number = 0
        # Unknown sorts after known, in both directions: "no bitrate reported" is not the
        # same as "the lowest bitrate", and treating it as either extreme would rank a
        # file by a fact nobody measured.
        unknown = 1 if number <= 0 else 0
        score = -min(number, 2_000_000_000) if number > 0 else 0
        if sorter.reversed:
            score = -score
        return (unknown, score)

    if sorter.field == "codec":
        try:
            rank = int(track.get("codec_rank") or 0)
        except (TypeError, ValueError):
            rank = 0
        return (-rank if sorter.reversed else rank,)

    text = str(actual or "").strip().lower()
    # Text with no configured value has no meaningful "best", so this is alphabetical and
    # only useful as a stable tiebreak. Empty sorts last either way.
    return (
        1 if not text else 0,
        *(tuple(-ord(ch) for ch in text[:32]) if sorter.reversed else tuple(ord(ch) for ch in text[:32])),
    )


def sort_key_for_track(sorters: list[TrackSorter], track: dict[str, Any]) -> tuple[int, ...]:
    """The whole key, in the operator's order, ending in the track index.

    The index is always last and never configurable: it is what makes the ordering total,
    so two otherwise-identical tracks always resolve the same way rather than depending
    on dictionary order.
    """

    parts: list[int] = []
    for sorter in sorters:
        parts.extend(sorter_key_component(sorter, track))
    try:
        parts.append(int(track.get("index") or 0))
    except (TypeError, ValueError):
        parts.append(0)
    return tuple(parts)


# --- serialisation ------------------------------------------------------------------


def parse_sorters(raw: str | None) -> list[TrackSorter]:
    """Read a stored list. Anything unusable yields the seeded default rather than none.

    An empty list would mean "no ordering at all", which is never what a broken value
    should turn into — the file would be ranked by index alone and the operator would see
    a silently different answer.
    """

    text = (raw or "").strip()
    if not text:
        return list(DEFAULT_AUDIO_SORTERS)
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return list(DEFAULT_AUDIO_SORTERS)
    if not isinstance(data, list):
        return list(DEFAULT_AUDIO_SORTERS)
    out: list[TrackSorter] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        field = str(item.get("field") or "").strip().lower()
        if field not in SORTER_FIELDS:
            continue
        value = item.get("value")
        out.append(
            TrackSorter(
                field=field,
                value=str(value) if isinstance(value, str) and value.strip() else None,
                reversed=bool(item.get("reversed")),
            )
        )
    return out or list(DEFAULT_AUDIO_SORTERS)


def dump_sorters(sorters: list[TrackSorter]) -> str:
    return json.dumps(
        [{"field": s.field, "value": s.value, "reversed": s.reversed} for s in sorters],
        separators=(",", ":"),
    )


def validate_sorters(raw: str | None) -> str:
    """Validate a submitted list, refusing rather than silently dropping entries.

    A saved list quietly missing the field an operator typed would change how their files
    are ranked without telling them.
    """

    text = (raw or "").strip()
    if not text:
        return dump_sorters(list(DEFAULT_AUDIO_SORTERS))
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise TrackSorterError("The track sorter list is not valid JSON.") from exc
    if not isinstance(data, list):
        raise TrackSorterError("The track sorter list must be a list.")
    out: list[TrackSorter] = []
    for position, item in enumerate(data, start=1):
        if not isinstance(item, dict):
            raise TrackSorterError(f"Sorter {position} is not an object.")
        field = str(item.get("field") or "").strip().lower()
        if field not in SORTER_FIELDS:
            raise TrackSorterError(
                f"Sorter {position} uses an unknown field {field!r}. Known fields: {', '.join(SORTER_FIELDS)}."
            )
        value = item.get("value")
        out.append(
            TrackSorter(
                field=field,
                value=str(value) if isinstance(value, str) and value.strip() else None,
                reversed=bool(item.get("reversed")),
            )
        )
    return dump_sorters(out)


# --- the seeded default and the presets ---------------------------------------------

#: Exactly the ranking the fixed tuple applied: commentary demoted, then most channels,
#: then best codec, then most bitrate, then an existing default as a weak preference.
#: The index tiebreak is appended by ``sort_key_for_track`` and is not listed here.
DEFAULT_AUDIO_SORTERS: tuple[TrackSorter, ...] = (
    TrackSorter(field="commentary"),
    TrackSorter(field="channels"),
    TrackSorter(field="codec"),
    TrackSorter(field="bitrate"),
    TrackSorter(field="default"),
)

DEFAULT_SUBTITLE_SORTERS: tuple[TrackSorter, ...] = (
    TrackSorter(field="forced"),
    TrackSorter(field="default"),
    TrackSorter(field="language"),
)

#: The three existing policies, as starting points an operator can then edit. They are
#: presets rather than a separate mechanism, so "start from a policy and change one
#: thing" becomes possible instead of a code change.
PRESETS: dict[str, tuple[TrackSorter, ...]] = {
    "preferred_langs_quality": DEFAULT_AUDIO_SORTERS,
    "preferred_langs_strict": DEFAULT_AUDIO_SORTERS,
    "quality_all_languages": (
        TrackSorter(field="commentary"),
        TrackSorter(field="channels"),
        TrackSorter(field="codec"),
        TrackSorter(field="bitrate"),
    ),
}


def preset_sorters(name: str | None) -> list[TrackSorter]:
    return list(PRESETS.get((name or "").strip().lower(), DEFAULT_AUDIO_SORTERS))


def describe_sorters(sorters: list[TrackSorter]) -> str:
    """A sentence for the selection notes.

    Refiner already explains *why* it picked a track, which FileFlows does not. That
    explanation has to keep working now the ranking is data-driven, so it describes the
    configured list rather than a fixed sentence about a fixed tuple.
    """

    if not sorters:
        return "no ordering configured, so tracks were taken in file order"
    return ", then ".join(s.describe() for s in sorters)
