"""DB reachability + Alembic head check for scripts/verify-local.ps1 (no API required)."""

from __future__ import annotations

import os
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
_BACKEND = _REPO_ROOT / "apps" / "backend"


def main() -> int:
    url = (os.environ.get("MEDIAMOP_DATABASE_URL") or "").strip()
    if not url:
        print("FAIL: MEDIAMOP_DATABASE_URL is not set.", file=sys.stderr)
        return 2

    try:
        from alembic.config import Config
        from alembic.runtime.migration import MigrationContext
        from alembic.script import ScriptDirectory
        from sqlalchemy import create_engine, text
    except ImportError as exc:
        print(f"FAIL: missing dependency ({exc}). Install apps/backend with pip install -e .", file=sys.stderr)
        return 2

    ini_path = _BACKEND / "alembic.ini"
    if not ini_path.is_file():
        print(f"FAIL: missing {ini_path}", file=sys.stderr)
        return 2

    cfg = Config(str(ini_path))
    script = ScriptDirectory.from_config(cfg)
    heads = script.get_heads()
    if len(heads) != 1:
        print(f"FAIL: expected a single Alembic head, got {heads!r}", file=sys.stderr)
        return 2
    head = heads[0]

    try:
        eng = create_engine(url)
        with eng.connect() as conn:
            conn.execute(text("SELECT 1"))
            ctx = MigrationContext.configure(conn)
            current = ctx.get_current_revision()
    except Exception as exc:
        print(f"FAIL: database connection or migration context: {exc}", file=sys.stderr)
        return 3

    if current != head:
        print(
            f"FAIL: Alembic not at head (current={current!r}, head={head!r}). "
            r"Run: .\scripts\dev-migrate.ps1",
            file=sys.stderr,
        )
        return 4

    print("OK: database reachable and revision matches Alembic head.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
