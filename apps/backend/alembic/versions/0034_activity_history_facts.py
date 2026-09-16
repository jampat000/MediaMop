"""Activity history that can be filtered and that has a stated horizon (#469).

Adds the facts people filter by as columns on ``activity_events`` — ``trigger``, ``result``,
``library_id``, ``relative_path``, ``run_key`` — and fills them for events already recorded. Adds
``suite_settings.activity_retention_days`` (default 90): Activity was never pruned before, so the
first prune after upgrading removes events older than 90 days. James decided that on 2026-09-17.

The classifier used for the backfill is a frozen copy, not an import: a migration that imports a
live function changes its own history the next time that function is edited.

Revision ID: 0034_activity_history_facts
Revises: 0033_refiner_library_media_type
"""

from __future__ import annotations

import json

import sqlalchemy as sa
from sqlalchemy import inspect

from alembic import op

revision = "0034_activity_history_facts"
down_revision = "0033_refiner_library_media_type"
branch_labels = None
depends_on = None

_TRIGGERS = {"manual", "scheduled", "startup", "worker", "retry", "system", "webhook", "folder_change"}
_RESULTS = {"success", "skipped", "warning", "retrying", "running", "failed"}
_RESULT_BY_TYPE_WORD = (
    ("failed", "failed"),
    ("failure", "failed"),
    ("denied", "failed"),
    ("fell_back", "warning"),
    ("skipped", "skipped"),
    ("progress", "running"),
    ("started", "running"),
    ("succeeded", "success"),
    ("completed", "success"),
    ("passed_through", "success"),
    ("rejected", "success"),
    ("reported", "success"),
    ("cancelled", "success"),
)
_BATCH = 1000


def _columns(table: str) -> set[str]:
    return {c["name"] for c in inspect(op.get_bind()).get_columns(table)}


def _indexes(table: str) -> set[str]:
    return {i["name"] for i in inspect(op.get_bind()).get_indexes(table)}


def _facts(event_type: str, detail: str | None) -> dict[str, object]:
    data: dict = {}
    text = (detail or "").strip()
    if text.startswith("{"):
        try:
            parsed = json.loads(text)
            data = parsed if isinstance(parsed, dict) else {}
        except ValueError:
            data = {}
    trigger = data.get("trigger")
    trigger = trigger.strip().lower() if isinstance(trigger, str) and trigger.strip().lower() in _TRIGGERS else None
    result = data.get("result")
    result = result.strip().lower() if isinstance(result, str) and result.strip().lower() in _RESULTS else None
    if result is None and data.get("ok") is False:
        result = "failed"
    if result is None:
        lowered = (event_type or "").lower()
        result = next((value for word, value in _RESULT_BY_TYPE_WORD if word in lowered), None)
    library_id = data.get("library_id")
    library_id = library_id if isinstance(library_id, int) and not isinstance(library_id, bool) else None
    path = data.get("relative_media_path")
    path = path.strip()[:2000] if isinstance(path, str) and path.strip() else None
    run_id = data.get("run_id")
    run_key = f"run:{run_id}"[:128] if isinstance(run_id, (str, int)) and str(run_id).strip() else None
    return {"trigger": trigger, "result": result, "library_id": library_id, "relative_path": path, "run_key": run_key}


def upgrade() -> None:
    existing = _columns("activity_events")
    for name, column in (
        ("trigger", sa.Column("trigger", sa.String(32), nullable=True)),
        ("result", sa.Column("result", sa.String(16), nullable=True)),
        ("library_id", sa.Column("library_id", sa.Integer(), nullable=True)),
        ("relative_path", sa.Column("relative_path", sa.Text(), nullable=True)),
        ("run_key", sa.Column("run_key", sa.String(128), nullable=True)),
    ):
        if name not in existing:
            op.add_column("activity_events", column)
    indexes = _indexes("activity_events")
    if "ix_activity_events_relative_path" not in indexes:
        op.create_index("ix_activity_events_relative_path", "activity_events", ["relative_path"])
    if "ix_activity_events_run_key" not in indexes:
        op.create_index("ix_activity_events_run_key", "activity_events", ["run_key"])

    if "activity_retention_days" not in _columns("suite_settings"):
        op.add_column(
            "suite_settings",
            sa.Column("activity_retention_days", sa.Integer(), nullable=False, server_default="90"),
        )

    bind = op.get_bind()
    last_id = 0
    while True:
        rows = bind.execute(
            sa.text(
                "select id, event_type, detail from activity_events where id > :last "
                "and trigger is null and result is null and relative_path is null order by id limit :n"
            ),
            {"last": last_id, "n": _BATCH},
        ).fetchall()
        if not rows:
            break
        for row_id, event_type, detail in rows:
            facts = _facts(event_type, detail)
            if any(value is not None for value in facts.values()):
                bind.execute(
                    sa.text(
                        "update activity_events set trigger = :trigger, result = :result, library_id = :library_id, "
                        "relative_path = :relative_path, run_key = :run_key where id = :id"
                    ),
                    {**facts, "id": row_id},
                )
            last_id = row_id


def downgrade() -> None:
    indexes = _indexes("activity_events")
    for index in ("ix_activity_events_run_key", "ix_activity_events_relative_path"):
        if index in indexes:
            op.drop_index(index, table_name="activity_events")
    existing = _columns("activity_events")
    with op.batch_alter_table("activity_events") as batch:
        for name in ("run_key", "relative_path", "library_id", "result", "trigger"):
            if name in existing:
                batch.drop_column(name)
    if "activity_retention_days" in _columns("suite_settings"):
        with op.batch_alter_table("suite_settings") as batch:
            batch.drop_column("activity_retention_days")
