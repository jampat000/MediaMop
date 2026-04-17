"""Pruner scope: optional JSON people-name include list for preview narrowing.

Revision ID: 0032_pruner_scope_preview_people_filters
Revises: 0031_pruner_scope_preview_genre_filters
Create Date: 2026-04-17
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0032_pruner_scope_preview_people_filters"
down_revision: str | None = "0031_pruner_scope_preview_genre_filters"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "pruner_scope_settings",
        sa.Column(
            "preview_include_people_json",
            sa.Text(),
            nullable=False,
            server_default=sa.text("'[]'"),
        ),
    )


def downgrade() -> None:
    op.drop_column("pruner_scope_settings", "preview_include_people_json")
