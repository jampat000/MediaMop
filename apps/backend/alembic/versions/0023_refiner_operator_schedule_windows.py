"""Refiner operator settings: per-scope schedule windows (Fetch parity, Refiner-only data).

Revision ID: 0023_refiner_operator_schedule_windows
Revises: 0022_refiner_operator_schedule_columns_backfill
Create Date: 2026-04-16
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0023_refiner_operator_schedule_windows"
down_revision: str | None = "0022_refiner_operator_schedule_columns_backfill"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "refiner_operator_settings",
        sa.Column("movie_schedule_hours_limited", sa.Integer(), nullable=False, server_default=sa.text("0")),
    )
    op.add_column(
        "refiner_operator_settings",
        sa.Column("movie_schedule_days", sa.Text(), nullable=False, server_default=sa.text("''")),
    )
    op.add_column(
        "refiner_operator_settings",
        sa.Column("movie_schedule_start", sa.Text(), nullable=False, server_default=sa.text("'00:00'")),
    )
    op.add_column(
        "refiner_operator_settings",
        sa.Column("movie_schedule_end", sa.Text(), nullable=False, server_default=sa.text("'23:59'")),
    )
    op.add_column(
        "refiner_operator_settings",
        sa.Column("tv_schedule_hours_limited", sa.Integer(), nullable=False, server_default=sa.text("0")),
    )
    op.add_column(
        "refiner_operator_settings",
        sa.Column("tv_schedule_days", sa.Text(), nullable=False, server_default=sa.text("''")),
    )
    op.add_column(
        "refiner_operator_settings",
        sa.Column("tv_schedule_start", sa.Text(), nullable=False, server_default=sa.text("'00:00'")),
    )
    op.add_column(
        "refiner_operator_settings",
        sa.Column("tv_schedule_end", sa.Text(), nullable=False, server_default=sa.text("'23:59'")),
    )


def downgrade() -> None:
    op.drop_column("refiner_operator_settings", "tv_schedule_end")
    op.drop_column("refiner_operator_settings", "tv_schedule_start")
    op.drop_column("refiner_operator_settings", "tv_schedule_days")
    op.drop_column("refiner_operator_settings", "tv_schedule_hours_limited")
    op.drop_column("refiner_operator_settings", "movie_schedule_end")
    op.drop_column("refiner_operator_settings", "movie_schedule_start")
    op.drop_column("refiner_operator_settings", "movie_schedule_days")
    op.drop_column("refiner_operator_settings", "movie_schedule_hours_limited")
