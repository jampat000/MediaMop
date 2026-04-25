from __future__ import annotations

import os
import re
import sys
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path


_DIST_INFO_RE = re.compile(r"^mediamop_backend-(?P<version>\d+(?:\.\d+)*)(?:[^\d].*)?\.dist-info$")


def _version_key(raw: str) -> tuple[int, ...]:
    return tuple(int(part) for part in raw.split(".") if part.isdigit())


def _packaged_resource_root() -> Path | None:
    if not getattr(sys, "frozen", False):
        return None
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        return Path(meipass)
    executable_dir = Path(sys.executable).resolve().parent
    internal_dir = executable_dir / "_internal"
    if internal_dir.is_dir():
        return internal_dir
    return executable_dir


def _packaged_dist_info_version() -> str | None:
    root = _packaged_resource_root()
    if root is None or not root.is_dir():
        return None

    versions: list[str] = []
    for child in root.iterdir():
        match = _DIST_INFO_RE.match(child.name)
        if match:
            versions.append(match.group("version"))
    if not versions:
        return None
    return sorted(versions, key=_version_key)[-1]


def get_version() -> str:
    env_version = (os.environ.get("MEDIAMOP_VERSION") or "").strip()
    if env_version:
        return env_version
    packaged_version = _packaged_dist_info_version()
    if packaged_version:
        return packaged_version
    try:
        pkg_version = (version("mediamop-backend") or "").strip()
        if pkg_version:
            return pkg_version
    except PackageNotFoundError:
        pass
    except Exception:
        pass
    return "1.0.0"


__version__ = get_version()
