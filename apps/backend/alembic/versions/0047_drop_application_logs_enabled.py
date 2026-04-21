"""Remove suite toggle for activity logging — events always record full detail.

Revision ID: 0047_drop_application_logs_enabled
Revises: 0046_suite_configuration_backup
Create Date: 2026-04-21
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0047_drop_application_logs_enabled"
down_revision: str | None = "0046_suite_configuration_backup"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_column("suite_settings", "application_logs_enabled")


def downgrade() -> None:
    op.add_column(
        "suite_settings",
        sa.Column("application_logs_enabled", sa.Boolean(), nullable=False, server_default=sa.text("1")),
    )
