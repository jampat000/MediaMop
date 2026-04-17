"""Pruner scope: watched movies rule toggle (Movies-tab preview/apply only).

Revision ID: 0030_pruner_watched_movies_scope
Revises: 0029_pruner_watched_tv_scope
Create Date: 2026-04-17
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0030_pruner_watched_movies_scope"
down_revision: str | None = "0029_pruner_watched_tv_scope"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "pruner_scope_settings",
        sa.Column("watched_movies_reported_enabled", sa.Boolean(), nullable=False, server_default=sa.text("0")),
    )


def downgrade() -> None:
    op.drop_column("pruner_scope_settings", "watched_movies_reported_enabled")
