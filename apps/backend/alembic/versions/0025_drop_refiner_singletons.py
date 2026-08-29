"""Drop the Refiner singleton settings tables

Exec-plan step 8 for ADR-0014. #333 moved every read to ``refiner_libraries``, and these
two tables survived one release on purpose: **the singleton was the rollback.** Dropping
it in the same release that introduced libraries would have left an install that hit a
problem with nothing to fall back to.

That release has shipped, so the reason to keep them is spent, and the reason to remove
them is not: two stores holding the same values is exactly the drift hazard #329 was
about, and the write-through keeping them in sync was a bridge rather than a design.

The scope-shaped API surfaces stay and are repointed at the libraries. The dashboard, the
Refiner overview and the setup wizard all read them, and the setup wizard writes through
one on first run — rewriting three screens to prove a storage change is not a trade worth
making when the hazard was the second store, not the shape.

Nothing is copied out first: ``0011`` seeded the libraries from these tables when it ran,
and ``mirror_singleton_paths_onto_seeded_libraries`` has kept them in step since. This
migration therefore drops rather than migrates, and it is **not reversible with data** —
the downgrade recreates the tables empty, which is stated rather than pretended otherwise.

Revision ID: 0025_drop_refiner_singletons
Revises: 0024_metadata_provider
Create Date: 2026-08-29 22:00:00
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy import inspect

from alembic import op

revision = "0025_drop_refiner_singletons"
down_revision = "0024_metadata_provider"
branch_labels = None
depends_on = None

_DROPPED = ("refiner_path_settings", "refiner_remux_rules_settings")


def _tables() -> set[str]:
    return set(inspect(op.get_bind()).get_table_names())


def upgrade() -> None:
    present = _tables()
    for name in _DROPPED:
        if name in present:
            op.drop_table(name)


def downgrade() -> None:
    # Recreated empty and with the columns the code that used them expected. A downgrade
    # gets the schema back, not the values — the values live on the libraries now, and
    # inventing them here would be worse than saying so.
    present = _tables()
    if "refiner_path_settings" not in present:
        op.create_table(
            "refiner_path_settings",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("refiner_watched_folder", sa.Text(), nullable=True),
            sa.Column("refiner_work_folder", sa.Text(), nullable=True),
            sa.Column("refiner_output_folder", sa.Text(), nullable=True),
            sa.Column("refiner_tv_watched_folder", sa.Text(), nullable=True),
            sa.Column("refiner_tv_work_folder", sa.Text(), nullable=True),
            sa.Column("refiner_tv_output_folder", sa.Text(), nullable=True),
            sa.Column(
                "movie_watched_folder_check_interval_seconds",
                sa.Integer(),
                nullable=False,
                server_default="300",
            ),
            sa.Column(
                "tv_watched_folder_check_interval_seconds",
                sa.Integer(),
                nullable=False,
                server_default="300",
            ),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.CheckConstraint("id = 1", name="ck_refiner_path_settings_singleton"),
        )
    if "refiner_remux_rules_settings" not in present:
        columns = [
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        ]
        for prefix in ("", "tv_"):
            columns.extend(
                [
                    sa.Column(f"{prefix}primary_audio_lang", sa.Text(), nullable=False, server_default="eng"),
                    sa.Column(f"{prefix}secondary_audio_lang", sa.Text(), nullable=False, server_default=""),
                    sa.Column(f"{prefix}tertiary_audio_lang", sa.Text(), nullable=False, server_default=""),
                    sa.Column(f"{prefix}default_audio_slot", sa.Text(), nullable=False, server_default="primary"),
                    sa.Column(f"{prefix}remove_commentary", sa.Integer(), nullable=False, server_default="1"),
                    sa.Column(f"{prefix}subtitle_mode", sa.Text(), nullable=False, server_default="remove_all"),
                    sa.Column(f"{prefix}subtitle_langs_csv", sa.Text(), nullable=False, server_default=""),
                    sa.Column(f"{prefix}preserve_forced_subs", sa.Integer(), nullable=False, server_default="1"),
                    sa.Column(f"{prefix}preserve_default_subs", sa.Integer(), nullable=False, server_default="1"),
                    sa.Column(
                        f"{prefix}audio_preference_mode",
                        sa.Text(),
                        nullable=False,
                        server_default="preferred_langs_quality",
                    ),
                ]
            )
        columns.append(sa.CheckConstraint("id = 1", name="ck_refiner_remux_rules_settings_singleton"))
        op.create_table("refiner_remux_rules_settings", *columns)
