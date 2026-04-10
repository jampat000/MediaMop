"""DB reachability + Alembic head check for scripts/verify-local.ps1 (no API required)."""

from __future__ import annotations

import os
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
_BACKEND = _REPO_ROOT / "apps" / "backend"
_SRC = _BACKEND / "src"


def main() -> int:
    if str(_SRC) not in sys.path:
        sys.path.insert(0, str(_SRC))

    try:
        from sqlalchemy import create_engine

        from mediamop.core.alembic_revision_check import DatabaseSchemaMismatch
        from mediamop.core.alembic_revision_check import ensure_database_at_application_head
        from mediamop.core.config import MediaMopSettings
    except ImportError as exc:
        print(f"FAIL: missing dependency ({exc}). Install apps/backend with pip install -e .", file=sys.stderr)
        return 2

    ini_path = _BACKEND / "alembic.ini"
    if not ini_path.is_file():
        print(f"FAIL: missing {ini_path}", file=sys.stderr)
        return 2

    try:
        url = MediaMopSettings.load().sqlalchemy_database_url
        eng = create_engine(url)
        ensure_database_at_application_head(eng)
    except DatabaseSchemaMismatch as exc:
        print(f"FAIL [{exc.kind}]: {exc}", file=sys.stderr)
        return 4
    except RuntimeError as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 2
    except Exception as exc:
        print(f"FAIL: database connection or migration context: {exc}", file=sys.stderr)
        return 3

    print("OK: database reachable and at Alembic head (upgraded when safely behind).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
