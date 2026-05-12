"""Add job-queue performance indexes and not_before retry-backoff column

Revision ID: 0007_indexes_and_retry_backoff
Revises: 0006_trusted_device_sessions
Create Date: 2026-05-12 00:00:00
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision = "0007_indexes_and_retry_backoff"
down_revision = "0006_trusted_device_sessions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = inspect(bind)

    for table in ("refiner_jobs", "pruner_jobs", "subber_jobs"):
        cols = {c["name"] for c in insp.get_columns(table)}
        if "not_before" not in cols:
            op.add_column(
                table,
                sa.Column("not_before", sa.DateTime(timezone=True), nullable=True),
            )

    for table, idx_name in (
        ("refiner_jobs", "ix_refiner_jobs_status_id"),
        ("pruner_jobs", "ix_pruner_jobs_status_id"),
        ("subber_jobs", "ix_subber_jobs_status_id"),
    ):
        idxs = {i["name"] for i in insp.get_indexes(table)}
        if idx_name not in idxs:
            op.create_index(idx_name, table, ["status", "id"])

    ae_idxs = {i["name"] for i in insp.get_indexes("activity_events")}
    if "ix_activity_events_created_at" not in ae_idxs:
        op.create_index("ix_activity_events_created_at", "activity_events", ["created_at"])
    if "ix_activity_events_module" not in ae_idxs:
        op.create_index("ix_activity_events_module", "activity_events", ["module"])


def downgrade() -> None:
    bind = op.get_bind()
    insp = inspect(bind)

    for idx_name, table in (
        ("ix_activity_events_module", "activity_events"),
        ("ix_activity_events_created_at", "activity_events"),
        ("ix_subber_jobs_status_id", "subber_jobs"),
        ("ix_pruner_jobs_status_id", "pruner_jobs"),
        ("ix_refiner_jobs_status_id", "refiner_jobs"),
    ):
        idxs = {i["name"] for i in insp.get_indexes(table)}
        if idx_name in idxs:
            op.drop_index(idx_name, table_name=table)

    for table in ("subber_jobs", "pruner_jobs", "refiner_jobs"):
        cols = {c["name"] for c in insp.get_columns(table)}
        if "not_before" in cols:
            op.drop_column(table, "not_before")
