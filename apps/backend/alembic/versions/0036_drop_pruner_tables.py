"""Drop the Pruner tables — Pruner moved to Deluno

Pruner removed items from Emby, Jellyfin and Plex libraries. That job now lives in
Deluno (#473), so the four tables it kept here have nothing left reading them.

Dropped rather than left in place, for the same reason ``0010`` dropped Subber's: a
schema that still lists ``pruner_scope_settings`` invites the next person to wonder
which half of the feature is missing. Pruner added no columns to shared tables, so
there is nothing to take off any table that stays.

What is dropped is Pruner's own bookkeeping — server connections, per-library rules,
preview snapshots and its job queue. No media file and no media-server library is
touched.

Revision ID: 0036_drop_pruner_tables
Revises: 0035_direct_play_facts
"""

from __future__ import annotations

from sqlalchemy import inspect

from alembic import op

revision = "0036_drop_pruner_tables"
down_revision = "0035_direct_play_facts"
branch_labels = None
depends_on = None

# Children before parents: scope settings reference preview runs and server instances,
# and preview runs reference server instances and jobs.
_TABLES = (
    "pruner_scope_settings",
    "pruner_preview_runs",
    "pruner_server_instances",
    "pruner_jobs",
)


def upgrade() -> None:
    existing = set(inspect(op.get_bind()).get_table_names())
    for table in _TABLES:
        if table in existing:
            op.drop_table(table)


def downgrade() -> None:
    # Nothing to restore. The models that described these tables went with the module,
    # and ``0001`` no longer creates them, so a database at ``0035`` built today has no
    # Pruner tables either: leaving them absent is the schema that revision now means.
    # A no-op rather than a refusal keeps the rest of the chain downgradable.
    pass
