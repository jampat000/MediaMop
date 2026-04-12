"""Fetcher Arr search cooldown log + schedule last-run state (singleton).

Cooldown rows use (app, action, item_type, item_id) with action scoped per job family
(missing vs upgrade), diverging from legacy Fetcher (app, item_type, item_id) only.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0007_fetcher_arr_search"
down_revision: str | None = "0006_fetcher_jobs_split"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)

    if not insp.has_table("fetcher_arr_action_log"):
        op.create_table(
            "fetcher_arr_action_log",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
            sa.Column("app", sa.String(length=16), nullable=False),
            sa.Column("action", sa.String(length=32), nullable=False),
            sa.Column("item_type", sa.String(length=16), nullable=False),
            sa.Column("item_id", sa.Integer(), nullable=False),
        )
        op.create_index(
            "ix_fetcher_arr_action_log_lookup",
            "fetcher_arr_action_log",
            ["app", "action", "item_type", "item_id", "created_at"],
        )
    else:
        idx_names = {ix["name"] for ix in insp.get_indexes("fetcher_arr_action_log")}
        if "ix_fetcher_arr_action_log_lookup" not in idx_names:
            op.create_index(
                "ix_fetcher_arr_action_log_lookup",
                "fetcher_arr_action_log",
                ["app", "action", "item_type", "item_id", "created_at"],
            )

    if not insp.has_table("fetcher_search_schedule_state"):
        op.create_table(
            "fetcher_search_schedule_state",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("sonarr_missing_last_run_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("sonarr_upgrade_last_run_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("radarr_missing_last_run_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("radarr_upgrade_last_run_at", sa.DateTime(timezone=True), nullable=True),
            sa.CheckConstraint("id = 1", name="ck_fetcher_search_schedule_state_singleton"),
        )
    op.execute(sa.text("INSERT OR IGNORE INTO fetcher_search_schedule_state (id) VALUES (1)"))


def downgrade() -> None:
    # IF EXISTS: downgrade after partial/manual schema drift must not hard-fail on missing objects.
    op.execute(sa.text("DROP TABLE IF EXISTS fetcher_search_schedule_state"))
    op.execute(sa.text("DROP INDEX IF EXISTS ix_fetcher_arr_action_log_lookup"))
    op.execute(sa.text("DROP TABLE IF EXISTS fetcher_arr_action_log"))
