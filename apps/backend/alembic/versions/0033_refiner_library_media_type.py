"""Rename a library's ``media_scope`` to ``media_type`` (#460).

The old name implied the module was still partitioned into Movies and TV, which ADR-0014 ended.
What the column holds is the library's type of media, and that is the word Deluno, Sonarr and
Radarr use for the same thing. Values are unchanged (``movie`` / ``tv``).

Revision ID: 0033_refiner_library_media_type
Revises: 0032_media_manager_handoffs
"""

from __future__ import annotations

from sqlalchemy import inspect

from alembic import op

revision = "0033_refiner_library_media_type"
down_revision = "0032_media_manager_handoffs"
branch_labels = None
depends_on = None


def _columns() -> set[str]:
    return {column["name"] for column in inspect(op.get_bind()).get_columns("refiner_libraries")}


# A plain RENAME COLUMN, deliberately not batch mode. Batch mode rebuilds the table (create, copy,
# drop, rename), and dropping refiner_libraries with foreign keys enforced would cascade-delete
# every library's manager links and file rows. SQLite has renamed columns in place since 3.25.


def upgrade() -> None:
    if "media_scope" in _columns() and "media_type" not in _columns():
        op.execute("ALTER TABLE refiner_libraries RENAME COLUMN media_scope TO media_type")


def downgrade() -> None:
    if "media_type" in _columns() and "media_scope" not in _columns():
        op.execute("ALTER TABLE refiner_libraries RENAME COLUMN media_type TO media_scope")
