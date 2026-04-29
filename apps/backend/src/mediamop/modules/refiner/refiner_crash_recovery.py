"""Refiner filesystem cleanup for interrupted file lifecycle operations."""

from __future__ import annotations

from pathlib import Path

from sqlalchemy.orm import Session

from mediamop.core.config import MediaMopSettings
from mediamop.modules.refiner.refiner_path_settings_model import RefinerPathSettingsRow


def cleanup_refiner_partial_output_files(session: Session, settings: MediaMopSettings) -> int:
    """Remove hidden ``*.partial`` files left by interrupted atomic output writes.

    MediaMop writes final outputs through hidden partial files and an atomic replace. On process
    startup there are no live workers yet, so any matching partial under configured Refiner output
    folders belongs to interrupted work and must not be exposed as success.
    """

    row = session.get(RefinerPathSettingsRow, 1)
    roots: set[Path] = set()
    if row is not None:
        for raw in (row.refiner_output_folder, row.refiner_tv_output_folder):
            text = (raw or "").strip()
            if text:
                roots.add(Path(text).expanduser())
    roots.add(Path(settings.mediamop_home).expanduser() / "refiner-output")

    removed = 0
    for root in roots:
        if not root.exists() or not root.is_dir():
            continue
        for partial in root.rglob(".*.partial"):
            if not partial.is_file():
                continue
            try:
                partial.unlink()
                removed += 1
            except OSError:
                continue
    return removed
