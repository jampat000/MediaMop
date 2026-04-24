from __future__ import annotations

import os
from importlib.metadata import PackageNotFoundError, version


def get_version() -> str:
    env_version = (os.environ.get("MEDIAMOP_VERSION") or "").strip()
    if env_version:
        return env_version
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
