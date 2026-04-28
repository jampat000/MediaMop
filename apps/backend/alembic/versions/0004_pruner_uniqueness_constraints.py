"""Pruner uniqueness constraints and normalized server URLs.

Revision ID: 0004_pruner_uniqueness_constraints
Revises: 0003_pruner_auto_apply_snapshot_limits
"""

from __future__ import annotations

from urllib.parse import urlparse, urlunparse

from alembic import op
import sqlalchemy as sa


revision: str = "0004_pruner_uniqueness_constraints"
down_revision: str | None = "0003_pruner_auto_apply_snapshot_limits"


def _normalize(raw: str) -> str:
    value = (raw or "").strip()
    parsed = urlparse(value if "://" in value else f"//{value}")
    scheme = (parsed.scheme or "http").lower()
    netloc = parsed.netloc or parsed.path.split("/", 1)[0]
    path = parsed.path if parsed.netloc else ("/" + parsed.path.split("/", 1)[1] if "/" in parsed.path else "")
    host = (parsed.hostname or netloc.split(":", 1)[0]).lower()
    port = parsed.port
    canon_netloc = host if port is None or (scheme == "http" and port == 80) or (scheme == "https" and port == 443) else f"{host}:{port}"
    return urlunparse((scheme, canon_netloc, path.rstrip("/"), "", "", "")).rstrip("/")


def upgrade() -> None:
    bind = op.get_bind()
    columns = {c["name"] for c in sa.inspect(bind).get_columns("pruner_server_instances")}
    if "normalized_base_url" not in columns:
        op.add_column(
            "pruner_server_instances",
            sa.Column("normalized_base_url", sa.String(length=512), nullable=False, server_default=""),
        )
    rows = list(bind.execute(sa.text("select id, provider, base_url from pruner_server_instances order by id asc")).mappings())
    seen: dict[tuple[str, str], int] = {}
    for row in rows:
        norm = _normalize(str(row["base_url"]))
        bind.execute(
            sa.text("update pruner_server_instances set normalized_base_url = :norm where id = :id"),
            {"norm": norm, "id": int(row["id"])},
        )
        key = (str(row["provider"]), norm)
        if key in seen:
            bind.execute(sa.text("delete from pruner_scope_settings where server_instance_id = :id"), {"id": int(row["id"])})
            bind.execute(sa.text("delete from pruner_preview_runs where server_instance_id = :id"), {"id": int(row["id"])})
            bind.execute(sa.text("delete from pruner_server_instances where id = :id"), {"id": int(row["id"])})
        else:
            seen[key] = int(row["id"])

    inspector = sa.inspect(bind)
    idx = {i["name"] for i in inspector.get_indexes("pruner_server_instances")}
    unique = {u["name"] for u in inspector.get_unique_constraints("pruner_server_instances")}
    if "uq_pruner_server_provider_normalized_url" not in idx and "uq_pruner_server_provider_normalized_url" not in unique:
        op.create_index(
            "uq_pruner_server_provider_normalized_url",
            "pruner_server_instances",
            ["provider", "normalized_base_url"],
            unique=True,
        )
    inspector = sa.inspect(bind)
    scope_idx = {i["name"] for i in inspector.get_indexes("pruner_scope_settings")}
    scope_unique = {u["name"] for u in inspector.get_unique_constraints("pruner_scope_settings")}
    if "uq_pruner_scope_instance_scope" not in scope_idx and "uq_pruner_scope_instance_scope" not in scope_unique:
        op.create_index(
            "uq_pruner_scope_instance_scope",
            "pruner_scope_settings",
            ["server_instance_id", "media_scope"],
            unique=True,
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    idx = {i["name"] for i in inspector.get_indexes("pruner_server_instances")}
    if "uq_pruner_server_provider_normalized_url" in idx:
        op.drop_index("uq_pruner_server_provider_normalized_url", table_name="pruner_server_instances")
    inspector = sa.inspect(bind)
    scope_idx = {i["name"] for i in inspector.get_indexes("pruner_scope_settings")}
    if "uq_pruner_scope_instance_scope" in scope_idx:
        op.drop_index("uq_pruner_scope_instance_scope", table_name="pruner_scope_settings")
    columns = {c["name"] for c in sa.inspect(bind).get_columns("pruner_server_instances")}
    if "normalized_base_url" in columns:
        op.drop_column("pruner_server_instances", "normalized_base_url")
