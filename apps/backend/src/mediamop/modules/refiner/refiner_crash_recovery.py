"""Refiner filesystem cleanup for interrupted file lifecycle operations."""

from __future__ import annotations

from pathlib import Path

from sqlalchemy.orm import Session

from mediamop.core.config import MediaMopSettings
from mediamop.modules.refiner.refiner_library_service import list_libraries


def cleanup_refiner_partial_output_files(session: Session, settings: MediaMopSettings) -> int:
    """Remove hidden ``*.partial`` files left by interrupted atomic output writes.

    MediaMop writes final outputs through hidden partial files and an atomic replace. On process
    startup there are no live workers yet, so any matching partial under configured Refiner output
    folders belongs to interrupted work and must not be exposed as success.
    """

    roots: set[Path] = set()
    for library in list_libraries(session):
        text = (library.output_folder or "").strip()
        if text:
            roots.add(Path(text).expanduser())
    # No fallback: the libraries are the only store now (#363). The default output root
    # below is still added unconditionally, so a database with no libraries at all still
    # gets its own partials swept.
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
