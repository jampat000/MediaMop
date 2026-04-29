"""Preflight guardrails for write-heavy media operations."""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path


BYTES_PER_MIB = 1024 * 1024


@dataclass(frozen=True)
class DiskSpaceCheck:
    ok: bool
    checked_path: Path
    free_mb: float
    required_mb: int
    message: str


def bytes_to_mb(size_bytes: int) -> float:
    return max(0.0, float(size_bytes) / float(BYTES_PER_MIB))


def mb_to_bytes(size_mb: int) -> int:
    return max(0, int(size_mb)) * BYTES_PER_MIB


def nearest_existing_parent(path: Path) -> Path:
    current = path if path.exists() and path.is_dir() else path.parent
    while not current.exists():
        parent = current.parent
        if parent == current:
            return current
        current = parent
    return current


def check_minimum_free_disk_space(*, target_path: Path, required_mb: int) -> DiskSpaceCheck:
    required = max(0, int(required_mb))
    checked = nearest_existing_parent(target_path)
    if required <= 0:
        return DiskSpaceCheck(
            ok=True,
            checked_path=checked,
            free_mb=0.0,
            required_mb=0,
            message="Disk-space guardrail disabled.",
        )
    usage = shutil.disk_usage(checked)
    free_mb = bytes_to_mb(int(usage.free))
    ok = free_mb >= float(required)
    if ok:
        message = f"Target drive has enough free space ({free_mb:.1f} MB >= {required} MB required)."
    else:
        message = f"Skipped: insufficient disk space on target drive ({free_mb / 1024:.1f} GB < {required / 1024:.1f} GB required)."
    return DiskSpaceCheck(
        ok=ok,
        checked_path=checked,
        free_mb=free_mb,
        required_mb=required,
        message=message,
    )
