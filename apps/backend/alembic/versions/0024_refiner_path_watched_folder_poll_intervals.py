"""Per-scope watched-folder poll intervals on path settings; drop global operator duplicate.

Revision ID: 0024_refiner_path_watched_folder_poll_intervals
Revises: 0023_refiner_operator_schedule_windows
Create Date: 2026-04-16
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0024_refiner_path_watched_folder_poll_intervals"
down_revision: str | None = "0023_refiner_operator_schedule_windows"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "refiner_path_settings",
        sa.Column("movie_watched_folder_check_interval_seconds", sa.Integer(), nullable=False, server_default=sa.text("300")),
    )
    op.add_column(
        "refiner_path_settings",
        sa.Column("tv_watched_folder_check_interval_seconds", sa.Integer(), nullable=False, server_default=sa.text("300")),
    )
    op.execute(
        """
        UPDATE refiner_path_settings
        SET
          movie_watched_folder_check_interval_seconds = (
            SELECT watched_folder_check_interval_seconds FROM refiner_operator_settings WHERE id = 1
          ),
          tv_watched_folder_check_interval_seconds = (
            SELECT watched_folder_check_interval_seconds FROM refiner_operator_settings WHERE id = 1
          )
        WHERE id = 1
        """
    )
    op.drop_column("refiner_operator_settings", "watched_folder_check_interval_seconds")


def downgrade() -> None:
    op.add_column(
        "refiner_operator_settings",
        sa.Column("watched_folder_check_interval_seconds", sa.Integer(), nullable=False, server_default=sa.text("300")),
    )
    op.execute(
        """
        UPDATE refiner_operator_settings
        SET watched_folder_check_interval_seconds = COALESCE(
          (SELECT movie_watched_folder_check_interval_seconds FROM refiner_path_settings WHERE id = 1),
          300
        )
        WHERE id = 1
        """
    )
    op.drop_column("refiner_path_settings", "tv_watched_folder_check_interval_seconds")
    op.drop_column("refiner_path_settings", "movie_watched_folder_check_interval_seconds")
