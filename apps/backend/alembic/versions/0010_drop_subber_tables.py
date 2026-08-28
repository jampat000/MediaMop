"""Drop the Subber tables — Subber moved to Deluno

Subber fetched subtitles for a library MediaMop could only ever see through
Sonarr and Radarr. Deluno owns that library, so Subber lives there now and the
four tables it kept here have nothing left reading them.

Dropped rather than left in place. The columns 0009 leaves behind stay because
their table still carries live settings; these tables carry nothing else, and a
schema that still lists ``subber_settings`` invites the next person to wonder
which half of the feature is missing.

What is dropped is subtitle *bookkeeping* — which file has which subtitle, and
the queue that put it there. No subtitle file on disk is touched, and Deluno
reads what is beside the video for itself, so there is nothing here to migrate
anywhere.

Revision ID: 0010_drop_subber_tables
Revises: 0009_media_manager_connections
Create Date: 2026-08-28 00:00:00
"""

from __future__ import annotations

from sqlalchemy import inspect

from alembic import op

revision = "0010_drop_subber_tables"
down_revision = "0009_media_manager_connections"
branch_labels = None
depends_on = None

# Children before parents: subber_subtitle_state references the media rows.
_TABLES = (
    "subber_jobs",
    "subber_subtitle_state",
    "subber_providers",
    "subber_settings",
)


def upgrade() -> None:
    existing = set(inspect(op.get_bind()).get_table_names())
    for table in _TABLES:
        if table in existing:
            op.drop_table(table)


def downgrade() -> None:
    # One way. The models that described these tables went with the module, so
    # there is nothing left to rebuild them from, and an empty table would be a
    # worse lie than an absent one.
    msg = "Subber tables cannot be restored; Subber moved to Deluno."
    raise NotImplementedError(msg)
