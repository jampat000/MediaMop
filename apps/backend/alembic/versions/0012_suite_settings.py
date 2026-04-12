"""Singleton ``suite_settings`` for app-wide display text (not module integration).

Revision ID: 0012_suite_settings
Revises: 0011_refiner_path_settings
Create Date: 2026-04-12

"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0012_suite_settings"
down_revision: str | None = "0011_refiner_path_settings"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "suite_settings",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column(
            "product_display_name",
            sa.Text(),
            nullable=False,
            server_default=sa.text("'MediaMop'"),
        ),
        sa.Column("signed_in_home_notice", sa.Text(), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.CheckConstraint("id = 1", name="ck_suite_settings_singleton"),
        sa.PrimaryKeyConstraint("id", name="pk_suite_settings"),
    )
    op.execute(
        sa.text(
            "INSERT INTO suite_settings (id, product_display_name, signed_in_home_notice, updated_at) "
            "VALUES (1, 'MediaMop', NULL, CURRENT_TIMESTAMP)"
        )
    )


def downgrade() -> None:
    op.drop_table("suite_settings")
