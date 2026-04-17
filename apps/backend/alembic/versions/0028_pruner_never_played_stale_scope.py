"""Pruner scope: never-played stale rule toggles and age threshold.

Revision ID: 0028_pruner_never_played_stale_scope
Revises: 0027_pruner_scope_scheduled_preview
Create Date: 2026-04-17
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0028_pruner_never_played_stale_scope"
down_revision: str | None = "0027_pruner_scope_scheduled_preview"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "pruner_scope_settings",
        sa.Column("never_played_stale_reported_enabled", sa.Boolean(), nullable=False, server_default=sa.text("0")),
    )
    op.add_column(
        "pruner_scope_settings",
        sa.Column("never_played_min_age_days", sa.Integer(), nullable=False, server_default=sa.text("90")),
    )


def downgrade() -> None:
    op.drop_column("pruner_scope_settings", "never_played_min_age_days")
    op.drop_column("pruner_scope_settings", "never_played_stale_reported_enabled")
