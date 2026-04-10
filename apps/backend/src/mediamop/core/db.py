"""Canonical SQLAlchemy 2.x database foundation — SQLite-first (Alembic-compatible).

Sync engine + :class:`sessionmaker` keep request handling predictable. The engine is always
created from :attr:`MediaMopSettings.sqlalchemy_database_url` (file-backed SQLite under
``MEDIAMOP_HOME`` / ``MEDIAMOP_DB_PATH``). Connection-level PRAGMAs enforce WAL, foreign keys,
busy timeout, and a sane synchronous mode.
"""

from __future__ import annotations

from sqlalchemy import MetaData, create_engine, event, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from mediamop.core.config import MediaMopSettings

# Explicit naming convention keeps FK/PK/ix names stable across Alembic autogenerates.
_NAMING_CONVENTION: dict[str, str] = {
    "ix": "ix_%(table_name)s_%(column_0_N_name)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(referred_table_name)s_%(column_0_N_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    """Declarative base for MediaMop schema — all platform/module models register here."""

    metadata = MetaData(naming_convention=_NAMING_CONVENTION)


def _register_sqlite_pragmas(engine: Engine) -> None:
    """Apply SQLite hardening on every new DB-API connection (not only process startup)."""

    @event.listens_for(engine, "connect")
    def _sqlite_connect(dbapi_connection: object, _connection_record: object) -> None:
        cursor = dbapi_connection.cursor()
        try:
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.execute("PRAGMA busy_timeout=5000")
            cursor.execute("PRAGMA synchronous=NORMAL")
        finally:
            cursor.close()


def create_db_engine(settings: MediaMopSettings) -> Engine:
    """Return a sync SQLite engine for the configured database path."""

    url = settings.sqlalchemy_database_url
    if not url.startswith("sqlite:"):
        raise RuntimeError("MediaMop is SQLite-only; expected sqlalchemy_database_url to be sqlite:…")
    engine = create_engine(
        url,
        connect_args={
            "check_same_thread": False,
            # Seconds sqlite3 waits on locked DB (complements PRAGMA busy_timeout).
            "timeout": 30.0,
        },
        pool_pre_ping=True,
        future=True,
    )
    _register_sqlite_pragmas(engine)
    return engine


def verify_sqlite_pragmas(engine: Engine) -> dict[str, str]:
    """Read PRAGMA values (for tests). Requires an open connection."""

    with engine.connect() as conn:
        jm = conn.execute(text("PRAGMA journal_mode")).scalar_one()
        fk = conn.execute(text("PRAGMA foreign_keys")).scalar_one()
        bt = conn.execute(text("PRAGMA busy_timeout")).scalar_one()
        sync = conn.execute(text("PRAGMA synchronous")).scalar_one()
    return {
        "journal_mode": str(jm),
        "foreign_keys": str(fk),
        "busy_timeout": str(bt),
        "synchronous": str(sync),
    }


def create_session_factory(engine: Engine) -> sessionmaker[Session]:
    """Thread-safe session factory bound to *engine*."""

    return sessionmaker(
        bind=engine,
        class_=Session,
        autoflush=False,
        autocommit=False,
        expire_on_commit=False,
        future=True,
    )


def dispose_engine(engine: Engine | None) -> None:
    if engine is not None:
        engine.dispose()
