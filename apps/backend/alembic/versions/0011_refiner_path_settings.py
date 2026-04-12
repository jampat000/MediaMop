"""Singleton ``refiner_path_settings`` row for Refiner watched/work/output folders.

Revision ID: 0011_refiner_path_settings
Revises: 0010_subber_jobs
Create Date: 2026-04-11

"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0011_refiner_path_settings"
down_revision: str | None = "0010_subber_jobs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "refiner_path_settings",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("refiner_watched_folder", sa.Text(), nullable=True),
        sa.Column("refiner_work_folder", sa.Text(), nullable=True),
        sa.Column(
            "refiner_output_folder",
            sa.Text(),
            nullable=False,
            server_default=sa.text("''"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.CheckConstraint("id = 1", name="ck_refiner_path_settings_singleton"),
        sa.PrimaryKeyConstraint("id", name="pk_refiner_path_settings"),
    )
    op.execute(
        sa.text(
            "INSERT INTO refiner_path_settings "
            "(id, refiner_watched_folder, refiner_work_folder, refiner_output_folder, updated_at) "
            "VALUES (1, NULL, NULL, '', CURRENT_TIMESTAMP)"
        )
    )


def downgrade() -> None:
    op.drop_table("refiner_path_settings")
