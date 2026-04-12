"""Refiner domain: pure ownership vs upstream blocking (no *arr HTTP, no orchestration).

Ownership can be explicit (``applies_to_file``) or anchor-based (title + year after
normalization and packaging-token stripping). Blocking only consults activity flags on
rows that already apply to the file under the same relevance rule — it never infers
ownership from activity.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Sequence

# Movie release years only; deterministic cutoffs for 4-digit tokens.
_YEAR_MIN = 1888
_YEAR_MAX = 2035

# Packaging / technical tokens removed before anchor comparison.
# Deliberately single-word: multi-word sources are folded in ``normalize_titleish``.
_PACKAGING_TOKENS: frozenset[str] = frozenset(
    {
        # resolution / scan labels
        "480p",
        "576p",
        "720p",
        "900p",
        "1080p",
        "1080i",
        "1440p",
        "2160p",
        "4320p",
        "4k",
        "8k",
        "5k",
        "uhd",
        "fhd",
        "hq",
        "sd",
        "full",
        "hdr",
        "hdr10",
        "hdr10plus",
        "dolby",
        "vision",
        # codecs / encode noise
        "x264",
        "x265",
        "h264",
        "h265",
        "hevc",
        "av1",
        "avc",
        "divx",
        "xvidx",
        "mpeg2",
        "mpeg4",
        "aac",
        "opus",
        "ac3",
        "eac3",
        "dts",
        "truehd",
        "atmos",
        "flac",
        # source / format
        "bluray",
        "bdrip",
        "brrip",
        "dvdrip",
        "dvd",
        "webdl",
        "webrip",
        "hdtv",
        "pdtv",
        "sdtv",
        "dsrip",
        "cam",
        "telesync",
        "telecine",
        "workprint",
        "remux",
        "hybrid",
        # release metadata (non-title)
        "repack",
        "proper",
        "internal",
        "retail",
        "extended",
        "unrated",
        "remastered",
        "multi",
        "dual",
        "dubbed",
        "subbed",
        "subs",
        "readnfo",
        "nfofix",
        # common group / indexer noise (not exhaustive; expand as needed)
        "yts",
        "yify",
        "rarbg",
        "ettv",
        "eztv",
        "sparks",
        "geckos",
        "megusta",
        "ethd",
        "ntb",
        "fgt",
        "amzn",
        "nf",
        "hulu",
        "dsnp",
        "atvp",
    }
)


@dataclass(frozen=True, slots=True)
class TitleYearAnchor:
    """Order-independent title anchor plus a single release year (movie ownership)."""

    title_tokens: frozenset[str]
    year: int | None

    def is_usable_for_match(self) -> bool:
        return bool(self.title_tokens) and self.year is not None


@dataclass(frozen=True, slots=True)
class FileAnchorCandidate:
    """File-side strings for anchor ownership (callers map paths / release names here)."""

    title: str
    year: int | None = None


@dataclass(frozen=True, slots=True)
class RefinerQueueRowView:
    """One upstream queue row after the caller has mapped *arr data.

    - ``applies_to_file``: explicit path/id/title association. When True, the row
      applies regardless of anchor strings. Use for import-pending and hard links.
    - ``queue_title`` / ``queue_year``: optional queue-side strings for anchor
      ownership when ``applies_to_file`` is False. ``queue_year`` overrides parsing
      from ``queue_title`` for the year anchor only.
    - ``is_upstream_active``, ``is_import_pending``, ``blocking_suppressed_for_import_wait``:
      blocking and metadata only; never used to decide ownership.
    """

    applies_to_file: bool
    is_upstream_active: bool
    is_import_pending: bool
    blocking_suppressed_for_import_wait: bool = False
    queue_title: str | None = None
    queue_year: int | None = None


def normalize_titleish(raw: str) -> str:
    """Lowercase, fold common hyphenated release tokens, keep alphanumerics as word tokens."""
    s = raw.lower().strip()
    s = s.replace("blu-ray", "bluray")
    s = s.replace("web-dl", "webdl")
    # Multi-token indexer / group suffixes (fold before ``[^a-z0-9]+``) so they cannot
    # veto title+year anchor equality; do not strip bare ``am`` (e.g. "I Am Legend").
    s = re.sub(r"\byts[\s.\-]+am\b", " ", s)
    s = re.sub(r"[^a-z0-9]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def tokenize_normalized(normalized: str) -> list[str]:
    if not normalized:
        return []
    return [t for t in normalized.split() if t]


def strip_packaging_tokens(tokens: Sequence[str]) -> list[str]:
    """Remove technical/packaging tokens; never used to veto — only to isolate anchors."""
    return [t for t in tokens if t not in _PACKAGING_TOKENS]


def _is_year_token(t: str) -> bool:
    if len(t) != 4 or not t.isdigit():
        return False
    y = int(t)
    return _YEAR_MIN <= y <= _YEAR_MAX


def extract_title_tokens_and_year(
    tokens: Sequence[str],
    *,
    explicit_year: int | None,
) -> tuple[list[str], int | None]:
    """Split stripped tokens into title anchor tokens and a single year.

    With ``explicit_year``, that year wins and a token equal to its string form is
    dropped from the title set. Otherwise the last valid 4-digit year token in order
    is the year and is removed from the title tokens (deterministic).
    """
    toks = list(tokens)
    if explicit_year is not None:
        ys = str(explicit_year)
        title = [t for t in toks if t != ys]
        return title, explicit_year
    year_indices = [i for i, t in enumerate(toks) if _is_year_token(t)]
    if not year_indices:
        return toks, None
    idx = year_indices[-1]
    year = int(toks[idx])
    title = [t for i, t in enumerate(toks) if i != idx]
    return title, year


def extract_title_year_anchor(
    raw: str,
    *,
    explicit_year: int | None = None,
) -> TitleYearAnchor | None:
    """Strip packaging noise, then build a title-token set and optional year.

    Returns None when there is no non-empty raw string. Otherwise returns an anchor
    (possibly unusable for matching if title tokens are empty or year is missing).
    """
    if not raw or not raw.strip():
        return None
    normalized = normalize_titleish(raw)
    toks = tokenize_normalized(normalized)
    stripped = strip_packaging_tokens(toks)
    title_toks, year = extract_title_tokens_and_year(stripped, explicit_year=explicit_year)
    return TitleYearAnchor(frozenset(title_toks), year)


def title_year_anchors_match(a: TitleYearAnchor, b: TitleYearAnchor) -> bool:
    """True when both anchors are usable and agree on title tokens and year."""
    return (
        a.is_usable_for_match()
        and b.is_usable_for_match()
        and a.title_tokens == b.title_tokens
        and a.year == b.year
    )


def _row_anchor(row: RefinerQueueRowView) -> TitleYearAnchor | None:
    if row.queue_title is None or not row.queue_title.strip():
        return None
    return extract_title_year_anchor(row.queue_title, explicit_year=row.queue_year)


def _file_anchor(candidate: FileAnchorCandidate) -> TitleYearAnchor | None:
    return extract_title_year_anchor(candidate.title, explicit_year=candidate.year)


def row_owns_by_title_year_anchor(
    row: RefinerQueueRowView,
    file_candidate: FileAnchorCandidate,
) -> bool:
    """Ownership via anchor only — ignores ``applies_to_file``."""
    qa = _row_anchor(row)
    fa = _file_anchor(file_candidate)
    if qa is None or fa is None:
        return False
    return title_year_anchors_match(qa, fa)


def _row_applies_to_candidate(
    row: RefinerQueueRowView,
    file_candidate: FileAnchorCandidate | None,
) -> bool:
    if row.applies_to_file:
        return True
    if file_candidate is None:
        return False
    return row_owns_by_title_year_anchor(row, file_candidate)


def file_is_owned_by_queue(
    rows: Sequence[RefinerQueueRowView],
    *,
    file_candidate: FileAnchorCandidate | None = None,
) -> bool:
    """True if any row applies: explicit signal or matching title/year anchors.

    import-pending rows still count when ``applies_to_file`` is True, or when anchors
    match. Never consults ``is_upstream_active``.
    """
    return any(_row_applies_to_candidate(r, file_candidate) for r in rows)


def should_block_for_upstream(
    rows: Sequence[RefinerQueueRowView],
    *,
    file_candidate: FileAnchorCandidate | None = None,
) -> bool:
    """True if any *applicable* active row requests a wait (suppression respected).

    Applicability matches :func:`file_is_owned_by_queue` for the same candidate.
    """
    return any(
        _row_applies_to_candidate(r, file_candidate)
        and r.is_upstream_active
        and not r.blocking_suppressed_for_import_wait
        for r in rows
    )