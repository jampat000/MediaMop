"""Pruner scope: preview-only year, studio, and collection include filters.

Revision ID: 0034_pruner_scope_preview_year_studio_collection
Revises: 0033_pruner_movies_low_rating_unwatched_stale
Create Date: 2026-04-17
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0034_pruner_scope_preview_year_studio_collection"
down_revision: str | None = "0033_pruner_movies_low_rating_unwatched_stale"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("pruner_scope_settings", sa.Column("preview_year_min", sa.Integer(), nullable=True))
    op.add_column("pruner_scope_settings", sa.Column("preview_year_max", sa.Integer(), nullable=True))
    op.add_column(
        "pruner_scope_settings",
        sa.Column(
            "preview_include_studios_json",
            sa.Text(),
            nullable=False,
            server_default=sa.text("'[]'"),
        ),
    )
    op.add_column(
        "pruner_scope_settings",
        sa.Column(
            "preview_include_collections_json",
            sa.Text(),
            nullable=False,
            server_default=sa.text("'[]'"),
        ),
    )


def downgrade() -> None:
    op.drop_column("pruner_scope_settings", "preview_include_collections_json")
    op.drop_column("pruner_scope_settings", "preview_include_studios_json")
    op.drop_column("pruner_scope_settings", "preview_year_max")
    op.drop_column("pruner_scope_settings", "preview_year_min")
