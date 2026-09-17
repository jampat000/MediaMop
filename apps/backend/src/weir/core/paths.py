"""Product-owned filesystem root for Weir (Phase 10).

This path is **not** an implicit “data lives next to the Git checkout”, **not** another product’s AppData layout, and **not**
derived from the process current working directory unless ``WEIR_HOME`` explicitly
uses a relative segment (discouraged).

Defaults:
- **Windows:** ``%PROGRAMDATA%\\Weir`` (normally ``C:\\ProgramData\\Weir``)
- **Unix:** ``$XDG_DATA_HOME/weir`` if set, else ``~/.local/share/weir``

Future runtime artifacts (logs, cache, local exports) should live under this root; nothing
in this module creates subdirectories yet — configuration only.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path


def default_weir_home() -> Path:
    """OS-appropriate default when ``WEIR_HOME`` is unset."""

    if sys.platform == "win32":
        base = (os.environ.get("PROGRAMDATA") or r"C:\ProgramData").strip()
        return Path(base) / "Weir"
    xdg = (os.environ.get("XDG_DATA_HOME") or "").strip()
    if xdg:
        return Path(xdg) / "weir"
    return Path.home() / ".local" / "share" / "weir"


def resolve_weir_home() -> Path:
    """Resolve canonical Weir home: env override or OS default."""

    override = (os.environ.get("WEIR_HOME") or "").strip()
    if override:
        return Path(override).expanduser().resolve()
    return default_weir_home()
