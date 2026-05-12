"""Generic JSON/path helpers for *arr queue rows — no Radarr- or Sonarr-specific semantics.

Anything that interprets movie vs series, or which id fields apply, lives in the app
adapters instead.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any


def normalize_storage_path(path: str) -> str:
    """Normalize paths for equality (case-insensitive, forward slashes)."""
    return path.replace("\\", "/").strip().lower()


def first_str(row: Mapping[str, Any], *keys: str) -> str | None:
    for k in keys:
        v = row.get(k)
        if isinstance(v, str) and v.strip():
            return v.strip()
    return None


def first_int(row: Mapping[str, Any], *keys: str) -> int | None:
    for k in keys:
        v = row.get(k)
        if isinstance(v, bool):
            continue
        if isinstance(v, int):
            return v
        if isinstance(v, float) and v.is_integer():
            return int(v)
    return None


def nested_dict(row: Mapping[str, Any], key: str) -> Mapping[str, Any] | None:
    v = row.get(key)
    return v if isinstance(v, dict) else None


def primary_queue_status(row: Mapping[str, Any]) -> str:
    """First non-empty status-like string (Radarr/Sonarr v3 queue resources often align)."""
    for k in ("status", "trackedDownloadStatus", "trackedDownloadState"):
        v = row.get(k)
        if isinstance(v, str) and v.strip():
            return v.strip().lower()
    return ""


def output_path(row: Mapping[str, Any]) -> str | None:
    return first_str(row, "outputPath", "output_path")


def path_matches_candidate(row: Mapping[str, Any], candidate_path: str | None) -> bool:
    if candidate_path is None:
        return False
    out = output_path(row)
    if out is None:
        return False
    return normalize_storage_path(out) == normalize_storage_path(candidate_path)


def blocking_suppressed_for_import_wait(row: Mapping[str, Any]) -> bool:
    for k in (
        "blockingSuppressedForImportWait",
        "blocking_suppressed_for_import_wait",
        "mediamopBlockingSuppressedForImportWait",
    ):
        v = row.get(k)
        if isinstance(v, bool):
            return v
    return False
