"""Suite configuration auto-backup schedule and stored backup files (max 5).

Revision ID: 0046_suite_configuration_backup
Revises: 0045_broker_settings_proxy_key
Create Date: 2026-04-21
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0046_suite_configuration_backup"
down_revision: str | None = "0045_broker_settings_proxy_key"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "suite_configuration_backup",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("file_name", sa.Text(), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("file_name", name="uq_suite_configuration_backup_file_name"),
    )
    op.add_column(
        "suite_settings",
        sa.Column(
            "configuration_backup_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("0"),
        ),
    )
    op.add_column(
        "suite_settings",
        sa.Column(
            "configuration_backup_interval_hours",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("24"),
        ),
    )
    op.add_column(
        "suite_settings",
        sa.Column("configuration_backup_last_run_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("suite_settings", "configuration_backup_last_run_at")
    op.drop_column("suite_settings", "configuration_backup_interval_hours")
    op.drop_column("suite_settings", "configuration_backup_enabled")
    op.drop_table("suite_configuration_backup")
