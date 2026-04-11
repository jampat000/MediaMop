"""Pure classification of *arr failed-import / rejection status message blobs.

Precedence: any terminal rejection signal beats pending/waiting-only text in the same
blob. Among terminals, the first rule in :data:`_TERMINAL_RULE_ORDER` wins.

This module is *arr-domain rules only* (no Refiner/Fetcher runtime). Refiner and Fetcher
both consume it without importing each other.
"""

from __future__ import annotations

import re
from enum import Enum
from typing import Final


class FailedImportOutcome(str, Enum):
    """Locked MediaMop taxonomy for failed import / queue rejection explanations."""

    QUALITY = "QUALITY"
    UNMATCHED = "UNMATCHED"
    CORRUPT = "CORRUPT"
    DOWNLOAD_FAILED = "DOWNLOAD_FAILED"
    IMPORT_FAILED = "IMPORT_FAILED"
    PENDING_WAITING = "PENDING_WAITING"
    UNKNOWN = "UNKNOWN"


def normalize_failed_import_blob(text: str) -> str:
    """Lowercase and collapse whitespace for deterministic substring checks."""
    s = text.strip().lower()
    return re.sub(r"\s+", " ", s)


# Substrings after normalization. Order within :data:`_TERMINAL_RULE_ORDER` is the
# tie-break when multiple terminal phrases appear in one blob.
_TERMINAL_RULE_ORDER: Final[
    tuple[tuple[FailedImportOutcome, tuple[str, ...]], ...]
] = (
    (
        FailedImportOutcome.QUALITY,
        ("not an upgrade for existing movie file",),
    ),
    (
        FailedImportOutcome.UNMATCHED,
        ("manual import required",),
    ),
    (
        FailedImportOutcome.CORRUPT,
        (
            "file is corrupt",
            "corrupt file",
            "corrupt download",
            "unreadable",
            "failed integrity check",
            "checksum failed",
            "hash check failed",
        ),
    ),
    (
        FailedImportOutcome.DOWNLOAD_FAILED,
        (
            "download client failed",
            "download failed",
            "failure for usenet download",
            "failure for torrent download",
            "unable to connect to the remote download client",
            "download client unavailable",
            "download client is unavailable",
        ),
    ),
    (
        FailedImportOutcome.IMPORT_FAILED,
        (
            "import failed",
            "failed to import",
            "error importing",
            "could not import",
            "couldn't import",
            "not a valid",
        ),
    ),
)

_PENDING_PHRASES: Final[tuple[str, ...]] = (
    "downloaded - waiting to import",
    "waiting to import",
    "import pending",
)


def classify_failed_import_message(blob: str) -> FailedImportOutcome:
    """Classify a single message blob (may concatenate multiple *arr status lines).

    Terminal outcomes are evaluated first; :attr:`FailedImportOutcome.PENDING_WAITING`
    applies only when no terminal substring matches. :attr:`FailedImportOutcome.UNKNOWN`
    applies when nothing matches after normalization.
    """
    n = normalize_failed_import_blob(blob)
    if not n:
        return FailedImportOutcome.UNKNOWN

    for outcome, needles in _TERMINAL_RULE_ORDER:
        if any(needle in n for needle in needles):
            return outcome

    for needle in _PENDING_PHRASES:
        if needle in n:
            return FailedImportOutcome.PENDING_WAITING

    return FailedImportOutcome.UNKNOWN
