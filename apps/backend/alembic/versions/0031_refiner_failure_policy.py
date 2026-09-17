"""What a library does once a file has used up its retries.

Weir sits in the middle of a pipeline it does not own. A file that fails processing used to
stay in Weir's hands for good, which meant it never reached the media manager — the user's
media simply went missing, and Weir was the reason.

``pass_through`` (the new default) hands the original back unmodified. ``hold`` keeps the old
behaviour. Every existing library moves to ``pass_through``: that is the product's guarantee, and
an install that upgrades should get it without having to find the setting.

Revision ID: 0031_refiner_failure_policy
Revises: 0030_refiner_file_media_facts
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy import inspect

from alembic import op

revision = "0031_refiner_failure_policy"
down_revision = "0030_refiner_file_media_facts"
branch_labels = None
depends_on = None


def _columns() -> set[str]:
    return {column["name"] for column in inspect(op.get_bind()).get_columns("refiner_libraries")}


def upgrade() -> None:
    if "failure_policy" not in _columns():
        op.add_column(
            "refiner_libraries",
            sa.Column("failure_policy", sa.Text(), nullable=False, server_default="pass_through"),
        )


def downgrade() -> None:
    if "failure_policy" in _columns():
        op.drop_column("refiner_libraries", "failure_policy")
