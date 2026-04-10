"""SQLite-first runtime directories under ``MEDIAMOP_HOME`` (Stage 10).

Default layout (when overrides are unset):

- ``{home}/data/mediamop.sqlite3`` — database file (via ``MEDIAMOP_DB_PATH`` default)
- ``{home}/backups/``
- ``{home}/logs/``
- ``{home}/temp/``
"""

from __future__ import annotations

import os
from pathlib import Path

from mediamop.core.paths import resolve_mediamop_home


def _env_path(name: str) -> str | None:
    raw = (os.environ.get(name) or "").strip()
    return raw or None


def resolve_db_path(home: Path) -> Path:
    """Absolute path to the SQLite database file."""

    override = _env_path("MEDIAMOP_DB_PATH")
    if override:
        p = Path(override).expanduser()
        if not p.is_absolute():
            return (home / p).resolve()
        return p.resolve()
    return (home / "data" / "mediamop.sqlite3").resolve()


def resolve_backup_dir(home: Path) -> Path:
    override = _env_path("MEDIAMOP_BACKUP_DIR")
    if override:
        p = Path(override).expanduser()
        if not p.is_absolute():
            return (home / p).resolve()
        return p.resolve()
    return (home / "backups").resolve()


def resolve_log_dir(home: Path) -> Path:
    override = _env_path("MEDIAMOP_LOG_DIR")
    if override:
        p = Path(override).expanduser()
        if not p.is_absolute():
            return (home / p).resolve()
        return p.resolve()
    return (home / "logs").resolve()


def resolve_temp_dir(home: Path) -> Path:
    override = _env_path("MEDIAMOP_TEMP_DIR")
    if override:
        p = Path(override).expanduser()
        if not p.is_absolute():
            return (home / p).resolve()
        return p.resolve()
    return (home / "temp").resolve()


def ensure_runtime_directories(
    *,
    db_path: Path,
    backup_dir: Path,
    log_dir: Path,
    temp_dir: Path,
) -> None:
    """Create parent of DB file and standard runtime dirs (idempotent)."""

    backup_dir.mkdir(parents=True, exist_ok=True)
    log_dir.mkdir(parents=True, exist_ok=True)
    temp_dir.mkdir(parents=True, exist_ok=True)
    db_path.parent.mkdir(parents=True, exist_ok=True)


def resolve_all_runtime_paths() -> tuple[Path, Path, Path, Path, Path]:
    """Return ``(home, db_path, backup_dir, log_dir, temp_dir)`` — all absolute."""

    home = resolve_mediamop_home()
    return (
        home.resolve(),
        resolve_db_path(home),
        resolve_backup_dir(home),
        resolve_log_dir(home),
        resolve_temp_dir(home),
    )


def sqlalchemy_sqlite_url(db_path: Path) -> str:
    """SQLAlchemy URL for a file-backed SQLite database (POSIX path in URL)."""

    return "sqlite:///" + db_path.resolve().as_posix()
