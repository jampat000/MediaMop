"""Backfill Refiner operator schedule columns on existing installs.

Revision ID: 0022_refiner_operator_schedule_columns_backfill
Revises: 0021_refiner_operator_settings
Create Date: 2026-04-15
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0022_refiner_operator_schedule_columns_backfill"
down_revision: str | None = "0021_refiner_operator_settings"
branch_labels = None
depends_on = None


def _has_column(table_name: str, column_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return any(col.get("name") == column_name for col in inspector.get_columns(table_name))


def upgrade() -> None:
    if not _has_column("refiner_operator_settings", "movie_schedule_enabled"):
        op.add_column(
            "refiner_operator_settings",
            sa.Column("movie_schedule_enabled", sa.Integer(), nullable=False, server_default=sa.text("1")),
        )
    if not _has_column("refiner_operator_settings", "movie_schedule_interval_seconds"):
        op.add_column(
            "refiner_operator_settings",
            sa.Column("movie_schedule_interval_seconds", sa.Integer(), nullable=False, server_default=sa.text("300")),
        )
    if not _has_column("refiner_operator_settings", "tv_schedule_enabled"):
        op.add_column(
            "refiner_operator_settings",
            sa.Column("tv_schedule_enabled", sa.Integer(), nullable=False, server_default=sa.text("1")),
        )
    if not _has_column("refiner_operator_settings", "tv_schedule_interval_seconds"):
        op.add_column(
            "refiner_operator_settings",
            sa.Column("tv_schedule_interval_seconds", sa.Integer(), nullable=False, server_default=sa.text("300")),
        )


def downgrade() -> None:
    if _has_column("refiner_operator_settings", "tv_schedule_interval_seconds"):
        op.drop_column("refiner_operator_settings", "tv_schedule_interval_seconds")
    if _has_column("refiner_operator_settings", "tv_schedule_enabled"):
        op.drop_column("refiner_operator_settings", "tv_schedule_enabled")
    if _has_column("refiner_operator_settings", "movie_schedule_interval_seconds"):
        op.drop_column("refiner_operator_settings", "movie_schedule_interval_seconds")
    if _has_column("refiner_operator_settings", "movie_schedule_enabled"):
        op.drop_column("refiner_operator_settings", "movie_schedule_enabled")
