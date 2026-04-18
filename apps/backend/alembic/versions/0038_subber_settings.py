"""Subber singleton settings (OpenSubtitles, Sonarr, Radarr, preferences, schedules).

Revision ID: 0038_subber_settings
Revises: 0037_pruner_scope_scheduled_preview_window
Create Date: 2026-04-18
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0038_subber_settings"
down_revision: str | None = "0037_pruner_scope_scheduled_preview_window"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "subber_settings",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("enabled", sa.Boolean(), server_default=sa.text("0"), nullable=False),
        sa.Column("opensubtitles_username", sa.String(length=255), server_default="", nullable=False),
        sa.Column("opensubtitles_credentials_ciphertext", sa.Text(), server_default="", nullable=False),
        sa.Column("sonarr_base_url", sa.String(length=500), server_default="", nullable=False),
        sa.Column("sonarr_credentials_ciphertext", sa.Text(), server_default="", nullable=False),
        sa.Column("radarr_base_url", sa.String(length=500), server_default="", nullable=False),
        sa.Column("radarr_credentials_ciphertext", sa.Text(), server_default="", nullable=False),
        sa.Column(
            "language_preferences_json",
            sa.Text(),
            server_default=sa.text("'[\"en\"]'"),
            nullable=False,
        ),
        sa.Column("subtitle_folder", sa.String(length=1000), server_default="", nullable=False),
        sa.Column("tv_schedule_enabled", sa.Boolean(), server_default=sa.text("0"), nullable=False),
        sa.Column(
            "tv_schedule_interval_seconds",
            sa.Integer(),
            server_default=sa.text("21600"),
            nullable=False,
        ),
        sa.Column("tv_schedule_hours_limited", sa.Boolean(), server_default=sa.text("0"), nullable=False),
        sa.Column("tv_schedule_days", sa.String(length=200), server_default="", nullable=False),
        sa.Column("tv_schedule_start", sa.String(length=5), server_default="00:00", nullable=False),
        sa.Column("tv_schedule_end", sa.String(length=5), server_default="23:59", nullable=False),
        sa.Column("movies_schedule_enabled", sa.Boolean(), server_default=sa.text("0"), nullable=False),
        sa.Column(
            "movies_schedule_interval_seconds",
            sa.Integer(),
            server_default=sa.text("21600"),
            nullable=False,
        ),
        sa.Column("movies_schedule_hours_limited", sa.Boolean(), server_default=sa.text("0"), nullable=False),
        sa.Column("movies_schedule_days", sa.String(length=200), server_default="", nullable=False),
        sa.Column("movies_schedule_start", sa.String(length=5), server_default="00:00", nullable=False),
        sa.Column("movies_schedule_end", sa.String(length=5), server_default="23:59", nullable=False),
        sa.Column(
            "tv_last_scheduled_scan_enqueued_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column(
            "movies_last_scheduled_scan_enqueued_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
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
        sa.CheckConstraint("id = 1", name="ck_subber_settings_singleton"),
        sa.PrimaryKeyConstraint("id", name="pk_subber_settings"),
    )


def downgrade() -> None:
    op.drop_table("subber_settings")
