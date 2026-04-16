"""Add singleton Refiner operator automation settings.

Revision ID: 0021_refiner_operator_settings
Revises: 0020_refiner_tv_remux_rules_settings
Create Date: 2026-04-15
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0021_refiner_operator_settings"
down_revision: str | None = "0020_refiner_tv_remux_rules_settings"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "refiner_operator_settings",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("max_concurrent_files", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.Column("watched_folder_check_interval_seconds", sa.Integer(), nullable=False, server_default=sa.text("300")),
        sa.Column("min_file_age_seconds", sa.Integer(), nullable=False, server_default=sa.text("60")),
        sa.Column("movie_schedule_enabled", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.Column("movie_schedule_interval_seconds", sa.Integer(), nullable=False, server_default=sa.text("300")),
        sa.Column("tv_schedule_enabled", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.Column("tv_schedule_interval_seconds", sa.Integer(), nullable=False, server_default=sa.text("300")),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.CheckConstraint("id = 1", name="ck_refiner_operator_settings_singleton"),
        sa.PrimaryKeyConstraint("id", name="pk_refiner_operator_settings"),
    )
    op.execute(
        sa.text(
            "INSERT INTO refiner_operator_settings "
            "(id, max_concurrent_files, watched_folder_check_interval_seconds, min_file_age_seconds, "
            "movie_schedule_enabled, movie_schedule_interval_seconds, tv_schedule_enabled, tv_schedule_interval_seconds, updated_at) "
            "VALUES (1, 1, 300, 60, 1, 300, 1, 300, CURRENT_TIMESTAMP)"
        )
    )


def downgrade() -> None:
    op.drop_table("refiner_operator_settings")
