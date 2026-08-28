"""Initial MediaMop schema (SQLite, ORM-aligned).

Creates every table registered on ``Base.metadata`` for greenfield installs, then seeds
singleton configuration rows (suite, *arr* library operator settings, Refiner paths/remux).

It builds from the live ORM metadata rather than a frozen DDL script, so what it creates
follows the models. When Subber moved to Deluno its four tables stopped being created
here; ``0007`` and ``0010`` both allow for their absence on a fresh database.
"""

from __future__ import annotations

from sqlalchemy.orm import Session, sessionmaker

import mediamop.modules.pruner.pruner_jobs_model  # noqa: F401
import mediamop.modules.pruner.pruner_preview_run_model  # noqa: F401
import mediamop.modules.pruner.pruner_scope_settings_model  # noqa: F401
import mediamop.modules.pruner.pruner_server_instance_model  # noqa: F401
import mediamop.modules.refiner.jobs_model  # noqa: F401
import mediamop.modules.refiner.refiner_operator_settings_model  # noqa: F401
import mediamop.modules.refiner.refiner_path_settings_model  # noqa: F401
import mediamop.modules.refiner.refiner_remux_rules_settings_model  # noqa: F401
import mediamop.platform.activity.models  # noqa: F401
import mediamop.platform.arr_library.arr_operator_settings_model  # noqa: F401
import mediamop.platform.auth.models  # noqa: F401
import mediamop.platform.suite_settings.model  # noqa: F401
import mediamop.platform.suite_settings.suite_configuration_backup_model  # noqa: F401
from alembic import op

# Register all ORM tables on Base.metadata (must mirror ``alembic/env.py``).
from mediamop.core.db import Base
from mediamop.core.greenfield_db_seed import seed_greenfield_singleton_rows

revision: str = "0001_mediamop_initial_schema"
down_revision: str | None = None


def upgrade() -> None:
    bind = op.get_bind()
    Base.metadata.create_all(bind=bind)
    factory = sessionmaker(bind=bind, class_=Session)
    with factory() as session:
        seed_greenfield_singleton_rows(session)
        session.commit()


def downgrade() -> None:
    bind = op.get_bind()
    Base.metadata.drop_all(bind=bind)
