"""Enforce SQLite schema revision: auto-upgrade known-behind DBs; fail clearly otherwise.

Shared by API startup and ``scripts/verify_local_db.py``.
"""

from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import text
from sqlalchemy.engine import Engine


class DatabaseSchemaMismatch(RuntimeError):
    """Recorded Alembic revision does not match this application (or upgrade failed)."""

    def __init__(self, message: str, *, kind: str) -> None:
        super().__init__(message)
        self.kind = kind


def _manual_migration_instructions() -> str:
    """Operator text for local installs on any OS (not only Windows PowerShell)."""

    return (
        "To apply migrations: from the repository root run .\\scripts\\dev-migrate.ps1 in PowerShell, "
        "or from apps/backend run PYTHONPATH=src python -m alembic upgrade head "
        "(on Windows, py -3 -m alembic upgrade head if python is not on PATH)."
    )


def _backend_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _alembic_config() -> Config:
    backend = _backend_root()
    ini = backend / "alembic.ini"
    if not ini.is_file():
        msg = f"Missing {ini}; cannot verify database schema revision."
        raise RuntimeError(msg)

    cfg = Config(str(ini))
    cfg.set_main_option("script_location", str(backend / "alembic"))
    return cfg


def _script_and_head() -> tuple[ScriptDirectory, str]:
    cfg = _alembic_config()
    script = ScriptDirectory.from_config(cfg)
    heads = script.get_heads()
    if len(heads) != 1:
        msg = f"Expected a single Alembic head, got {heads!r}."
        raise RuntimeError(msg)
    return script, heads[0]


def _current_revision(engine: Engine) -> str | None:
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))
        ctx = MigrationContext.configure(conn)
        return ctx.get_current_revision()


def _strictly_behind_head(script: ScriptDirectory, *, head: str, current: str) -> bool:
    """True if *current* is a strict ancestor of *head* on a linear down_revision chain."""

    rev = script.get_revision(head)
    seen: set[str] = set()
    while rev is not None and rev.revision not in seen:
        seen.add(rev.revision)
        dr = rev.down_revision
        if dr is None:
            break
        if isinstance(dr, tuple):
            return False
        if dr == current:
            return True
        rev = script.get_revision(dr)
    return False


def _run_alembic_upgrade_head() -> None:
    """Run ``alembic upgrade head`` (uses ``env.py`` + ``MediaMopSettings.load()`` for URL)."""

    cfg = _alembic_config()
    try:
        command.upgrade(cfg, "head")
    except Exception as exc:
        raise DatabaseSchemaMismatch(
            f"Alembic upgrade to head failed: {exc}. "
            "Fix the error above, or restore a database backup. "
            + _manual_migration_instructions(),
            kind="upgrade_failed",
        ) from exc


def ensure_database_at_application_head(engine: Engine) -> None:
    """Bring the DB to this build's Alembic head when safe; otherwise raise.

    - At head: no-op.
    - Known strict ancestor of head: run ``alembic upgrade head``, dispose *engine* pool, verify head.
    - Unversioned / unknown / incompatible: raise :class:`DatabaseSchemaMismatch` (no mutation).
    """

    script, head = _script_and_head()
    migrate_hint = _manual_migration_instructions()

    current = _current_revision(engine)
    if current == head:
        return

    if current is None:
        raise DatabaseSchemaMismatch(
            "No Alembic revision is recorded for this database (migrations have not been applied). "
            f"This build requires schema revision {head!r}. "
            + migrate_hint,
            kind="unversioned",
        )

    try:
        script.get_revision(current)
    except Exception as exc:
        raise DatabaseSchemaMismatch(
            f"Database revision {current!r} is not recognized by this MediaMop build "
            f"(expected head {head!r}). The database may come from a newer release; "
            "upgrade the application or restore a backup that matches this version.",
            kind="unknown_revision",
        ) from exc

    if _strictly_behind_head(script, head=head, current=current):
        _run_alembic_upgrade_head()
        engine.dispose()
        after = _current_revision(engine)
        if after != head:
            raise DatabaseSchemaMismatch(
                f"After upgrade, database revision is {after!r}, expected {head!r}. "
                + migrate_hint,
                kind="upgrade_failed",
            )
        return

    raise DatabaseSchemaMismatch(
        f"Database revision {current!r} does not match this build ({head!r}). "
        "Use a matching application version or run migrations if you downgraded the app.",
        kind="incompatible",
    )
