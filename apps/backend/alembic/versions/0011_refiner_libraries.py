"""Refiner libraries replace the fixed movie/tv scopes

Creates ``refiner_libraries``, ``refiner_rule_sets`` and the library/manager link table,
and seeds exactly two libraries — "Movies" and "TV" — from the existing singleton rows.

Every value is copied verbatim, including the two lists that used to be module constants
(the media extension allowlist and the downloader-staging markers), so an upgrade is a
behavioural no-op until an operator edits something. That is the hard constraint this
migration is answerable to (ADR-0014 §6), not a nice-to-have: a library's watched folder
is the input to source-folder deletion, so a path that moves without the operator asking
is destructive.

The seed lists are written out literally rather than imported from the modules they came
from. A migration that imports a live constant changes its own history the next time that
constant is edited.

Nothing reads these tables yet — that is the next step, which is where the no-op is
proven.

Revision ID: 0011_refiner_libraries
Revises: 0010_drop_subber_tables
Create Date: 2026-08-28 10:00:00
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy import inspect

from alembic import op

revision = "0011_refiner_libraries"
down_revision = "0010_drop_subber_tables"
branch_labels = None
depends_on = None

# Frozen copies of the constants as they stood when this migration was written.
_SEED_MEDIA_EXTENSIONS = ".avchd,.avi,.flv,.m4v,.mkv,.mov,.mp4,.mpe,.mpeg,.mpg,.webm,.wmv"
_SEED_EXCLUDE_MARKERS = ".sabnzbd,__admin__,_failed_,_repair_,_unpack_,incomplete"

# What the retired {"movie": "radarr", "tv": "sonarr"} inference would have chosen, in
# the order it would have chosen it: the scope-specific kind first, then a general one.
_SCOPE_KIND_PREFERENCE = {
    "movie": ("radarr", "deluno", "native"),
    "tv": ("sonarr", "deluno", "native"),
}


def _table_missing(bind: sa.engine.Connection, name: str) -> bool:
    return name not in set(inspect(bind).get_table_names())


def upgrade() -> None:
    bind = op.get_bind()
    existing = set(inspect(bind).get_table_names())

    if "refiner_rule_sets" not in existing:
        _create_rule_sets()
    if "refiner_libraries" not in existing:
        _create_libraries()
    if "refiner_library_manager_links" not in existing:
        _create_manager_links()

    _seed_from_singletons(bind)


def _create_rule_sets() -> None:
    op.create_table(
        "refiner_rule_sets",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("primary_audio_lang", sa.Text(), nullable=False, server_default=""),
        sa.Column("secondary_audio_lang", sa.Text(), nullable=False, server_default=""),
        sa.Column("tertiary_audio_lang", sa.Text(), nullable=False, server_default=""),
        sa.Column("default_audio_slot", sa.Text(), nullable=False, server_default="primary"),
        sa.Column("remove_commentary", sa.Boolean(), nullable=False, server_default="0"),
        sa.Column("subtitle_mode", sa.Text(), nullable=False, server_default="keep_all"),
        sa.Column("subtitle_langs_csv", sa.Text(), nullable=False, server_default=""),
        sa.Column("preserve_forced_subs", sa.Boolean(), nullable=False, server_default="1"),
        sa.Column("preserve_default_subs", sa.Boolean(), nullable=False, server_default="1"),
        sa.Column("audio_preference_mode", sa.Text(), nullable=False, server_default="preferred_langs_quality"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("name", name="uq_refiner_rule_sets_name"),
    )


def _create_libraries() -> None:
    op.create_table(
        "refiner_libraries",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default="1"),
        sa.Column("media_scope", sa.Text(), nullable=False, server_default="movie"),
        sa.Column("display_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("watched_folder", sa.Text(), nullable=False, server_default=""),
        sa.Column("work_folder", sa.Text(), nullable=False, server_default=""),
        sa.Column("output_folder", sa.Text(), nullable=False, server_default=""),
        sa.Column("media_extensions_csv", sa.Text(), nullable=False, server_default=""),
        sa.Column("exclude_markers_csv", sa.Text(), nullable=False, server_default=""),
        sa.Column("include_patterns_csv", sa.Text(), nullable=False, server_default=""),
        sa.Column("exclude_patterns_csv", sa.Text(), nullable=False, server_default=""),
        sa.Column("min_file_size_mb", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("max_file_size_mb", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("min_file_age_seconds", sa.Integer(), nullable=False, server_default="60"),
        sa.Column("exclude_hidden", sa.Boolean(), nullable=False, server_default="1"),
        sa.Column("top_level_only", sa.Boolean(), nullable=False, server_default="0"),
        sa.Column("scan_interval_seconds", sa.Integer(), nullable=False, server_default="300"),
        sa.Column("hold_minutes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("schedule_enabled", sa.Boolean(), nullable=False, server_default="1"),
        sa.Column("schedule_hours_limited", sa.Boolean(), nullable=False, server_default="0"),
        sa.Column("schedule_days", sa.Text(), nullable=False, server_default=""),
        sa.Column("schedule_start", sa.Text(), nullable=False, server_default="00:00"),
        sa.Column("schedule_end", sa.Text(), nullable=False, server_default="23:59"),
        sa.Column("max_concurrent_files", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "rule_set_id",
            sa.Integer(),
            sa.ForeignKey("refiner_rule_sets.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column(
            "discovered_from_connection_id",
            sa.Integer(),
            sa.ForeignKey("media_manager_connections.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("discovered_library_key", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("name", name="uq_refiner_libraries_name"),
    )


def _create_manager_links() -> None:
    op.create_table(
        "refiner_library_manager_links",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "library_id",
            sa.Integer(),
            sa.ForeignKey("refiner_libraries.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "connection_id",
            sa.Integer(),
            sa.ForeignKey("media_manager_connections.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.UniqueConstraint("library_id", "connection_id", name="uq_refiner_library_manager_links_pair"),
    )


def _one_row(bind: sa.engine.Connection, table: str) -> sa.Row | None:
    if _table_missing(bind, table):
        return None
    return bind.execute(sa.text(f"select * from {table} where id = 1")).mappings().first()  # noqa: S608


def _seed_from_singletons(bind: sa.engine.Connection) -> None:
    already = bind.execute(sa.text("select count(*) from refiner_libraries")).scalar() or 0
    if already:
        return

    paths = _one_row(bind, "refiner_path_settings")
    rules = _one_row(bind, "refiner_remux_rules_settings")
    ops = _one_row(bind, "refiner_operator_settings")

    def value(row: sa.RowMapping | None, key: str, fallback: object) -> object:
        if row is None:
            return fallback
        got = row.get(key)
        return fallback if got is None else got

    for scope, label, order in (("movie", "Movies", 0), ("tv", "TV", 1)):
        tv = scope == "tv"
        prefix = "tv_" if tv else ""

        rule_set_id = bind.execute(
            sa.text(
                "insert into refiner_rule_sets ("
                " name, primary_audio_lang, secondary_audio_lang, tertiary_audio_lang,"
                " default_audio_slot, remove_commentary, subtitle_mode, subtitle_langs_csv,"
                " preserve_forced_subs, preserve_default_subs, audio_preference_mode"
                ") values (:name, :p, :s, :t, :slot, :com, :submode, :sublangs, :forced, :dflt, :mode)"
            ),
            {
                "name": f"{label} rules",
                # The fallbacks are the shipped defaults, not empties. They were written
                # when the singleton always existed, so "nothing to read" could only mean
                # a half-built row. Since #363 removed those tables from 0001, a
                # greenfield install reaches here with nothing to read at all — and a new
                # install must get "eng", not a blank language preference.
                "p": value(rules, f"{prefix}primary_audio_lang", "eng"),
                "s": value(rules, f"{prefix}secondary_audio_lang", "jpn"),
                "t": value(rules, f"{prefix}tertiary_audio_lang", ""),
                "slot": value(rules, f"{prefix}default_audio_slot", "primary"),
                "com": int(bool(value(rules, f"{prefix}remove_commentary", 1))),
                "submode": value(rules, f"{prefix}subtitle_mode", "remove_all"),
                "sublangs": value(rules, f"{prefix}subtitle_langs_csv", ""),
                "forced": int(bool(value(rules, f"{prefix}preserve_forced_subs", 1))),
                "dflt": int(bool(value(rules, f"{prefix}preserve_default_subs", 1))),
                "mode": value(rules, f"{prefix}audio_preference_mode", "preferred_langs_quality"),
            },
        ).lastrowid

        watched_key = "refiner_tv_watched_folder" if tv else "refiner_watched_folder"
        work_key = "refiner_tv_work_folder" if tv else "refiner_work_folder"
        output_key = "refiner_tv_output_folder" if tv else "refiner_output_folder"
        interval_key = f"{'tv' if tv else 'movie'}_watched_folder_check_interval_seconds"

        library_id = bind.execute(
            sa.text(
                "insert into refiner_libraries ("
                " name, enabled, media_scope, display_order, watched_folder, work_folder, output_folder,"
                " media_extensions_csv, exclude_markers_csv, min_file_size_mb, min_file_age_seconds,"
                " scan_interval_seconds, schedule_enabled, schedule_hours_limited, schedule_days,"
                " schedule_start, schedule_end, max_concurrent_files, rule_set_id"
                ") values (:name, 1, :scope, :order, :watched, :work, :output,"
                " :exts, :markers, :minsize, :minage,"
                " :interval, :sched_on, :sched_limited, :sched_days,"
                " :sched_start, :sched_end, :concurrency, :rule_set_id)"
            ),
            {
                "name": label,
                "scope": scope,
                "order": order,
                "watched": value(paths, watched_key, ""),
                "work": value(paths, work_key, ""),
                "output": value(paths, output_key, ""),
                "exts": _SEED_MEDIA_EXTENSIONS,
                "markers": _SEED_EXCLUDE_MARKERS,
                # Guardrails were global; each seeded library inherits the same value, so
                # behaviour is unchanged until one is edited away from the others.
                "minsize": value(ops, "refiner_min_input_file_size_mb", 0),
                "minage": value(ops, "min_file_age_seconds", 60),
                "interval": value(paths, interval_key, 300),
                "sched_on": int(bool(value(ops, f"{'tv' if tv else 'movie'}_schedule_enabled", 1))),
                "sched_limited": int(bool(value(ops, f"{'tv' if tv else 'movie'}_schedule_hours_limited", 0))),
                "sched_days": value(ops, f"{'tv' if tv else 'movie'}_schedule_days", ""),
                "sched_start": value(ops, f"{'tv' if tv else 'movie'}_schedule_start", "00:00"),
                "sched_end": value(ops, f"{'tv' if tv else 'movie'}_schedule_end", "23:59"),
                "concurrency": value(ops, "max_concurrent_files", 1),
                "rule_set_id": rule_set_id,
            },
        ).lastrowid

        _link_seeded_manager(bind, library_id=library_id, scope=scope)


def _link_seeded_manager(bind: sa.engine.Connection, *, library_id: int, scope: str) -> None:
    """Link the connection the retired scope-to-kind inference would have picked."""

    if _table_missing(bind, "media_manager_connections"):
        return
    for kind in _SCOPE_KIND_PREFERENCE[scope]:
        row = bind.execute(
            sa.text(
                "select id from media_manager_connections"
                " where kind = :kind and enabled = 1 and base_url <> ''"
                " and api_key_ciphertext is not null and api_key_ciphertext <> ''"
                " order by id limit 1"
            ),
            {"kind": kind},
        ).first()
        if row is not None:
            bind.execute(
                sa.text("insert into refiner_library_manager_links (library_id, connection_id) values (:lib, :conn)"),
                {"lib": library_id, "conn": int(row[0])},
            )
            return


def downgrade() -> None:
    op.drop_table("refiner_library_manager_links")
    op.drop_table("refiner_libraries")
    op.drop_table("refiner_rule_sets")
