"""Product-owned filesystem root for MediaMop (Phase 10).

This path is **not** an implicit “data lives next to the Git checkout”, **not** another product’s AppData layout, and **not**
derived from the process current working directory unless ``MEDIAMOP_HOME`` explicitly
uses a relative segment (discouraged).

Defaults:
- **Windows:** ``%PROGRAMDATA%\\MediaMop`` (normally ``C:\\ProgramData\\MediaMop``)
- **Unix:** ``$XDG_DATA_HOME/mediamop`` if set, else ``~/.local/share/mediamop``

Future runtime artifacts (logs, cache, local exports) should live under this root; nothing
in this module creates subdirectories yet — configuration only.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path


def default_mediamop_home() -> Path:
    """OS-appropriate default when ``MEDIAMOP_HOME`` is unset."""

    if sys.platform == "win32":
        base = (os.environ.get("PROGRAMDATA") or r"C:\ProgramData").strip()
        return Path(base) / "MediaMop"
    xdg = (os.environ.get("XDG_DATA_HOME") or "").strip()
    if xdg:
        return Path(xdg) / "mediamop"
    return Path.home() / ".local" / "share" / "mediamop"


def resolve_mediamop_home() -> Path:
    """Resolve canonical MediaMop home: env override or OS default."""

    override = (os.environ.get("MEDIAMOP_HOME") or "").strip()
    if override:
        return Path(override).expanduser().resolve()
    return default_mediamop_home()
