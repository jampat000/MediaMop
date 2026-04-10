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
        from alembic.config import Config
        from alembic.runtime.migration import MigrationContext
        from alembic.script import ScriptDirectory
        from sqlalchemy import create_engine, text

        from mediamop.core.config import MediaMopSettings
    except ImportError as exc:
        print(f"FAIL: missing dependency ({exc}). Install apps/backend with pip install -e .", file=sys.stderr)
        return 2

    ini_path = _BACKEND / "alembic.ini"
    if not ini_path.is_file():
        print(f"FAIL: missing {ini_path}", file=sys.stderr)
        return 2

    # alembic.ini paths (script_location=alembic) resolve relative to cwd.
    old_cwd = os.getcwd()
    os.chdir(_BACKEND)
    try:
        cfg = Config("alembic.ini")
        script = ScriptDirectory.from_config(cfg)
        heads = script.get_heads()
    finally:
        os.chdir(old_cwd)
    if len(heads) != 1:
        print(f"FAIL: expected a single Alembic head, got {heads!r}", file=sys.stderr)
        return 2
    head = heads[0]

    try:
        url = MediaMopSettings.load().sqlalchemy_database_url
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
