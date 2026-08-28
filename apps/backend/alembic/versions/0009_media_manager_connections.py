"""Media manager connections become rows instead of per-vendor column pairs

Moves the Sonarr/Radarr connection and search-lane columns off the
``arr_library_operator_settings`` singleton and into ``media_manager_connections``
plus ``media_manager_search_lanes``.

Any configured connection is carried across, along with its two lanes, so an
instance that had Sonarr or Radarr set up keeps its settings under the new shape.
The old columns are left in place: dropping a column on SQLite means rebuilding the
table, and the settings row still carries unrelated values. A later migration can
remove them once nothing reads them.

Revision ID: 0009_media_manager_connections
Revises: 0008_notification_channels
Create Date: 2026-08-26 00:00:00
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy import inspect

from alembic import op

revision = "0009_media_manager_connections"
down_revision = "0008_notification_channels"
branch_labels = None
depends_on = None

_LEGACY_TABLE = "arr_library_operator_settings"


def _create_tables(insp: inspect) -> None:
    if "media_manager_connections" not in insp.get_table_names():
        op.create_table(
            "media_manager_connections",
            sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
            sa.Column("kind", sa.Text, nullable=False),
            sa.Column("name", sa.Text, nullable=False),
            sa.Column("enabled", sa.Boolean, nullable=False, server_default="1"),
            sa.Column("base_url", sa.Text, nullable=False, server_default=""),
            sa.Column("api_key_ciphertext", sa.Text, nullable=True),
            sa.Column("webhook_secret_ciphertext", sa.Text, nullable=True),
            sa.Column("last_connection_test_ok", sa.Boolean, nullable=True),
            sa.Column("last_connection_test_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("last_connection_test_detail", sa.Text, nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.UniqueConstraint("name", name="uq_media_manager_connections_name"),
        )

    if "media_manager_search_lanes" not in insp.get_table_names():
        op.create_table(
            "media_manager_search_lanes",
            sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
            sa.Column(
                "connection_id",
                sa.Integer,
                sa.ForeignKey("media_manager_connections.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("lane", sa.Text, nullable=False),
            sa.Column("enabled", sa.Boolean, nullable=False, server_default="0"),
            sa.Column("max_items_per_run", sa.Integer, nullable=False, server_default="50"),
            sa.Column("retry_delay_minutes", sa.Integer, nullable=False, server_default="1440"),
            sa.Column("schedule_enabled", sa.Boolean, nullable=False, server_default="0"),
            sa.Column("schedule_days", sa.Text, nullable=False, server_default=""),
            sa.Column("schedule_start", sa.Text, nullable=False, server_default="00:00"),
            sa.Column("schedule_end", sa.Text, nullable=False, server_default="23:59"),
            sa.Column("schedule_interval_seconds", sa.Integer, nullable=False, server_default="3600"),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.UniqueConstraint("connection_id", "lane", name="uq_media_manager_search_lanes_connection_lane"),
        )


def _carry_over(bind: sa.engine.Connection, insp: inspect) -> None:
    """Copy a configured Sonarr/Radarr connection into the new tables."""

    if _LEGACY_TABLE not in insp.get_table_names():
        return
    columns = {c["name"] for c in insp.get_columns(_LEGACY_TABLE)}

    for vendor, display in (("sonarr", "Sonarr"), ("radarr", "Radarr")):
        needed = {f"{vendor}_connection_base_url", f"{vendor}_connection_enabled"}
        if not needed <= columns:
            continue

        row = (
            bind.execute(
                sa.text(
                    f"SELECT {vendor}_connection_enabled AS enabled, "  # noqa: S608 - vendor is a literal above
                    f"{vendor}_connection_base_url AS base_url, "
                    f"{vendor}_connection_api_key_ciphertext AS api_key "
                    f"FROM {_LEGACY_TABLE} WHERE id = 1"
                )
            )
            .mappings()
            .first()
        )
        if row is None:
            continue

        base_url = (row["base_url"] or "").strip()
        api_key = row["api_key"]
        # Nothing configured means nothing worth creating a connection row for.
        if not base_url and not api_key:
            continue

        existing = bind.execute(
            sa.text("SELECT id FROM media_manager_connections WHERE name = :name"), {"name": display}
        ).first()
        if existing is not None:
            continue

        result = bind.execute(
            sa.text(
                "INSERT INTO media_manager_connections (kind, name, enabled, base_url, api_key_ciphertext) "
                "VALUES (:kind, :name, :enabled, :base_url, :api_key)"
            ),
            {
                "kind": vendor,
                "name": display,
                "enabled": 1 if row["enabled"] else 0,
                "base_url": base_url,
                "api_key": api_key,
            },
        )
        connection_id = result.lastrowid

        for lane in ("missing", "upgrade"):
            lane_columns = {
                key: f"{vendor}_{lane}_search_{key}"
                for key in (
                    "enabled",
                    "max_items_per_run",
                    "retry_delay_minutes",
                    "schedule_enabled",
                    "schedule_days",
                    "schedule_start",
                    "schedule_end",
                    "schedule_interval_seconds",
                )
            }
            if not set(lane_columns.values()) <= columns:
                continue
            select_list = ", ".join(f"{source} AS {alias}" for alias, source in lane_columns.items())
            lane_row = (
                bind.execute(sa.text(f"SELECT {select_list} FROM {_LEGACY_TABLE} WHERE id = 1"))  # noqa: S608
                .mappings()
                .first()
            )
            if lane_row is None:
                continue
            bind.execute(
                sa.text(
                    "INSERT INTO media_manager_search_lanes "
                    "(connection_id, lane, enabled, max_items_per_run, retry_delay_minutes, schedule_enabled, "
                    " schedule_days, schedule_start, schedule_end, schedule_interval_seconds) "
                    "VALUES (:connection_id, :lane, :enabled, :max_items, :retry, :sched, :days, :start, :end, :every)"
                ),
                {
                    "connection_id": connection_id,
                    "lane": lane,
                    "enabled": 1 if lane_row["enabled"] else 0,
                    "max_items": lane_row["max_items_per_run"],
                    "retry": lane_row["retry_delay_minutes"],
                    "sched": 1 if lane_row["schedule_enabled"] else 0,
                    "days": lane_row["schedule_days"],
                    "start": lane_row["schedule_start"],
                    "end": lane_row["schedule_end"],
                    "every": lane_row["schedule_interval_seconds"],
                },
            )


def upgrade() -> None:
    bind = op.get_bind()
    insp = inspect(bind)
    _create_tables(insp)
    _carry_over(bind, inspect(bind))


def downgrade() -> None:
    bind = op.get_bind()
    insp = inspect(bind)
    if "media_manager_search_lanes" in insp.get_table_names():
        op.drop_table("media_manager_search_lanes")
    if "media_manager_connections" in insp.get_table_names():
        op.drop_table("media_manager_connections")
