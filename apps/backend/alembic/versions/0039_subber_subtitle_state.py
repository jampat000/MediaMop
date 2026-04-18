"""Subber per-file subtitle tracking state.

Revision ID: 0039_subber_subtitle_state
Revises: 0038_subber_settings
Create Date: 2026-04-18
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0039_subber_subtitle_state"
down_revision: str | None = "0038_subber_settings"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "subber_subtitle_state",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("media_scope", sa.String(length=10), nullable=False),
        sa.Column("file_path", sa.String(length=2000), nullable=False),
        sa.Column("language_code", sa.String(length=10), nullable=False),
        sa.Column("status", sa.String(length=20), server_default="missing", nullable=False),
        sa.Column("subtitle_path", sa.String(length=2000), nullable=True),
        sa.Column("opensubtitles_file_id", sa.String(length=100), nullable=True),
        sa.Column("last_searched_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("search_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("source", sa.String(length=20), nullable=True),
        sa.Column("show_title", sa.String(length=500), nullable=True),
        sa.Column("season_number", sa.Integer(), nullable=True),
        sa.Column("episode_number", sa.Integer(), nullable=True),
        sa.Column("episode_title", sa.String(length=500), nullable=True),
        sa.Column("movie_title", sa.String(length=500), nullable=True),
        sa.Column("movie_year", sa.Integer(), nullable=True),
        sa.Column("sonarr_episode_id", sa.Integer(), nullable=True),
        sa.Column("radarr_movie_id", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name="pk_subber_subtitle_state"),
        sa.UniqueConstraint("file_path", "language_code", name="uq_subber_subtitle_state_file_lang"),
    )
    op.create_index(
        "ix_subber_subtitle_state_media_scope_status",
        "subber_subtitle_state",
        ["media_scope", "status"],
        unique=False,
    )
    op.create_index(
        "ix_subber_subtitle_state_tv_episode",
        "subber_subtitle_state",
        ["media_scope", "show_title", "season_number", "episode_number"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_subber_subtitle_state_tv_episode", table_name="subber_subtitle_state")
    op.drop_index("ix_subber_subtitle_state_media_scope_status", table_name="subber_subtitle_state")
    op.drop_table("subber_subtitle_state")
