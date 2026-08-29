"""A metadata provider connection, and original-language audio selection

Refiner picks audio from a fixed preference list. For a French film with English and
French audio, an ``eng``-first preference keeps **the dub**. Most people who care about
audio quality want the original, and nothing in MediaMop knew what the original was.

``suite_settings`` gains the provider connection. The key is stored encrypted with the
same helper the media manager credentials use, and the base URL is configurable rather
than hardcoded because an operator may put a cache or gateway in front of TMDb — a
Cloudflare worker is the common shape, and hardcoding the vendor address would make that
setup unusable.

``refiner_rule_sets`` gains the five options, all off by default. Nothing changes until an
operator opts in, and ``first_if_none`` is a safety net rather than a preference:
``plan_remux`` already refuses to write a file with no audio, and none of this may weaken
that.

Revision ID: 0024_metadata_provider
Revises: 0023_hardware_acceleration
Create Date: 2026-08-29 21:00:00
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy import inspect

from alembic import op

revision = "0024_metadata_provider"
down_revision = "0023_hardware_acceleration"
branch_labels = None
depends_on = None

_SUITE_COLUMNS: tuple[tuple[str, sa.Column], ...] = (
    (
        "metadata_provider",
        sa.Column("metadata_provider", sa.Text(), nullable=False, server_default=""),
    ),
    (
        "metadata_provider_base_url",
        sa.Column("metadata_provider_base_url", sa.Text(), nullable=False, server_default=""),
    ),
    (
        "metadata_provider_key_ciphertext",
        sa.Column("metadata_provider_key_ciphertext", sa.Text(), nullable=False, server_default=""),
    ),
)

_RULE_SET_COLUMNS: tuple[tuple[str, sa.Column], ...] = (
    (
        "keep_original_language",
        sa.Column("keep_original_language", sa.Boolean(), nullable=False, server_default="0"),
    ),
    (
        "original_language_additional_csv",
        sa.Column("original_language_additional_csv", sa.Text(), nullable=False, server_default=""),
    ),
    (
        "original_language_keep_only_first",
        sa.Column("original_language_keep_only_first", sa.Boolean(), nullable=False, server_default="1"),
    ),
    (
        "original_language_first_if_none",
        sa.Column("original_language_first_if_none", sa.Boolean(), nullable=False, server_default="1"),
    ),
    (
        "original_language_treat_empty_as_original",
        sa.Column("original_language_treat_empty_as_original", sa.Boolean(), nullable=False, server_default="0"),
    ),
)


def _columns(table: str) -> set[str]:
    inspector = inspect(op.get_bind())
    if table not in set(inspector.get_table_names()):
        return set()
    return {c["name"] for c in inspector.get_columns(table)}


def _add_missing(table: str, columns: tuple[tuple[str, sa.Column], ...]) -> None:
    present = _columns(table)
    if not present:
        return
    for name, column in columns:
        if name not in present:
            op.add_column(table, column)


def upgrade() -> None:
    _add_missing("suite_settings", _SUITE_COLUMNS)
    _add_missing("refiner_rule_sets", _RULE_SET_COLUMNS)


def downgrade() -> None:
    present = _columns("refiner_rule_sets")
    for name, _ in _RULE_SET_COLUMNS:
        if name in present:
            op.drop_column("refiner_rule_sets", name)
    present = _columns("suite_settings")
    for name, _ in _SUITE_COLUMNS:
        if name in present:
            op.drop_column("suite_settings", name)
