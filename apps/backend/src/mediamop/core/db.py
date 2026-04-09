"""Canonical SQLAlchemy 2.x database foundation (PostgreSQL-oriented; Alembic-compatible).

Sync engine + :class:`sessionmaker` keep request handling predictable (no async ORM pile-up
until there is a concrete reason). ``MEDIAMOP_DATABASE_URL`` drives the engine; when
unset, the app still starts and ``session_factory`` is ``None`` (see :mod:`mediamop.api.deps`).
"""

from __future__ import annotations

from sqlalchemy import MetaData, create_engine
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


def create_db_engine(settings: MediaMopSettings) -> Engine | None:
    """Return a sync engine when ``settings.database_url`` is set; otherwise ``None``."""

    if not settings.database_url:
        return None
    return create_engine(
        settings.database_url,
        pool_pre_ping=True,
        future=True,
    )


def create_session_factory(engine: Engine | None) -> sessionmaker[Session] | None:
    """Thread-safe session factory bound to *engine*; ``None`` if there is no engine."""

    if engine is None:
        return None
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
