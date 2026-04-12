"""Filesystem layout for ``trimmer.supplied_trim_plan.json_file_write.v1`` (Trimmer-owned under ``MEDIAMOP_HOME``)."""

from __future__ import annotations

from pathlib import Path


def trimmer_plan_exports_dir(mediamop_home: str) -> Path:
    """Directory ``<resolved home>/trimmer/plan_exports`` — JSON plan files are written only here."""

    home = Path(mediamop_home).expanduser().resolve()
    return home / "trimmer" / "plan_exports"
