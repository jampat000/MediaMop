"""Pruner scope: watched low-rating movies + unwatched stale movies (Movies tab, Jellyfin/Emby).

Revision ID: 0033_pruner_movies_low_rating_unwatched_stale
Revises: 0032_pruner_scope_preview_people_filters
Create Date: 2026-04-17
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0033_pruner_movies_low_rating_unwatched_stale"
down_revision: str | None = "0032_pruner_scope_preview_people_filters"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "pruner_scope_settings",
        sa.Column(
            "watched_movie_low_rating_reported_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("0"),
        ),
    )
    op.add_column(
        "pruner_scope_settings",
        sa.Column(
            "watched_movie_low_rating_max_community_rating",
            sa.Float(),
            nullable=False,
            server_default=sa.text("4.0"),
        ),
    )
    op.add_column(
        "pruner_scope_settings",
        sa.Column(
            "unwatched_movie_stale_reported_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("0"),
        ),
    )
    op.add_column(
        "pruner_scope_settings",
        sa.Column(
            "unwatched_movie_stale_min_age_days",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("90"),
        ),
    )


def downgrade() -> None:
    op.drop_column("pruner_scope_settings", "unwatched_movie_stale_min_age_days")
    op.drop_column("pruner_scope_settings", "unwatched_movie_stale_reported_enabled")
    op.drop_column("pruner_scope_settings", "watched_movie_low_rating_max_community_rating")
    op.drop_column("pruner_scope_settings", "watched_movie_low_rating_reported_enabled")
