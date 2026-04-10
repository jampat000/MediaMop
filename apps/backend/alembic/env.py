"""Alembic environment — uses mediamop.core.db.Base metadata."""

from __future__ import annotations

from logging.config import fileConfig
from pathlib import Path

from alembic import context

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None  # type: ignore[misc, assignment]

_backend_root = Path(__file__).resolve().parents[1]
_env_file = _backend_root / ".env"
if load_dotenv is not None and _env_file.is_file():
    load_dotenv(_env_file)

from sqlalchemy import engine_from_config, pool

# Import Base after ensuring src/ is on path (run from apps/backend with PYTHONPATH=src).
from mediamop.core.config import MediaMopSettings
from mediamop.core.db import Base

# Register models on Base.metadata (Alembic autogenerate / revision drift checks).
from mediamop.platform.activity import models as _activity_orm  # noqa: F401
from mediamop.platform.auth import models as _auth_orm  # noqa: F401
from mediamop.modules.refiner import jobs_model as _refiner_jobs_orm  # noqa: F401

# this is the Alembic Config object, which provides access to the values within alembic.ini
config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def get_url() -> str:
    """SQLite-first URL from ``MediaMopSettings`` (same resolution as the running API)."""

    return MediaMopSettings.load().sqlalchemy_database_url


def run_migrations_offline() -> None:
    url = get_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    ini_section = config.get_section(config.config_ini_section) or {}
    ini_section = {**ini_section, "sqlalchemy.url": get_url()}

    connectable = engine_from_config(
        ini_section,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
