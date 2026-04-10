"""SQLite-first runtime directories under ``MEDIAMOP_HOME`` (Stage 10).

Default layout (when overrides are unset):

- ``{home}/data/mediamop.sqlite3`` — database file (via ``MEDIAMOP_DB_PATH`` default)
- ``{home}/backups/``
- ``{home}/logs/``
- ``{home}/temp/``
"""

from __future__ import annotations

import os
import tempfile
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


def assert_sqlite_db_location_usable(db_path: Path) -> None:
    """Fail fast if the SQLite file path cannot be used read-write (local / packaged installs).

    - Rejects ``MEDIAMOP_DB_PATH`` resolving to an existing **directory** (common misconfiguration).
    - Verifies the parent directory allows creating a new file (writable volume / permissions).
    - If the DB file already exists, verifies it is a regular file and openable read-write.

    Call after :func:`ensure_runtime_directories` so the parent directory exists.
    """

    resolved = db_path.resolve()
    if resolved.exists() and resolved.is_dir():
        raise RuntimeError(
            f"SQLite database path must be a file, not a directory: {resolved}. "
            "Fix MEDIAMOP_DB_PATH or remove the directory at that location.",
        )
    if resolved.exists() and not resolved.is_file():
        raise RuntimeError(
            f"SQLite database path must be a regular file: {resolved}",
        )
    parent = resolved.parent
    try:
        with tempfile.NamedTemporaryFile(dir=parent, delete=True):
            pass
    except OSError as exc:
        raise RuntimeError(
            f"Cannot create files under database directory (check permissions and disk): {parent}",
        ) from exc
    if resolved.exists():
        try:
            with open(resolved, "r+b"):
                pass
        except OSError as exc:
            raise RuntimeError(
                f"SQLite database file exists but is not writable: {resolved}",
            ) from exc


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
