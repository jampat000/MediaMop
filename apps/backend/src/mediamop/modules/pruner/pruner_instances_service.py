"""Pruner server instances + default per-scope settings rows."""

from __future__ import annotations

from urllib.parse import urlparse, urlunparse

from sqlalchemy import select
from sqlalchemy.orm import Session

from mediamop.core.config import MediaMopSettings
from mediamop.modules.pruner.pruner_constants import MEDIA_SCOPE_MOVIES, MEDIA_SCOPE_TV
from mediamop.modules.pruner.pruner_credentials_envelope import (
    PrunerProvider,
    encrypt_envelope,
    envelope_secrets_for_provider,
)
from mediamop.modules.pruner.pruner_people_filters import preview_people_roles_to_db_column
from mediamop.modules.pruner.pruner_scope_settings_model import PrunerScopeSettings
from mediamop.modules.pruner.pruner_server_instance_model import PrunerServerInstance


def normalize_server_base_url(raw: str) -> str:
    """Canonical identity URL for duplicate detection: scheme/host lowercased, no trailing slash."""

    value = raw.strip()
    parsed = urlparse(value if "://" in value else f"//{value}")
    scheme = (parsed.scheme or "http").lower()
    netloc = parsed.netloc or parsed.path.split("/", 1)[0]
    path = parsed.path if parsed.netloc else ("/" + parsed.path.split("/", 1)[1] if "/" in parsed.path else "")
    if not netloc:
        msg = "base_url must include a host"
        raise ValueError(msg)
    host = (parsed.hostname or netloc.split(":", 1)[0]).lower()
    try:
        port = parsed.port
    except ValueError as e:
        msg = "base_url must include a valid port"
        raise ValueError(msg) from e
    if port is None or (scheme == "http" and port == 80) or (scheme == "https" and port == 443):
        canon_netloc = host
    else:
        canon_netloc = f"{host}:{port}"
    normalized = urlunparse((scheme, canon_netloc, path.rstrip("/"), "", "", "")).rstrip("/")
    return normalized


def ensure_scope_rows_for_instance(session: Session, server_instance_id: int) -> None:
    """Insert ``tv`` and ``movies`` scope rows if missing."""

    existing = session.scalars(
        select(PrunerScopeSettings.media_scope).where(
            PrunerScopeSettings.server_instance_id == server_instance_id,
        ),
    ).all()
    have = {str(x) for x in existing}
    for scope in (MEDIA_SCOPE_TV, MEDIA_SCOPE_MOVIES):
        if scope in have:
            continue
        session.add(
            PrunerScopeSettings(
                server_instance_id=server_instance_id,
                media_scope=scope,
                preview_include_people_roles_json=preview_people_roles_to_db_column([]),
            ),
        )


def create_server_instance(
    session: Session,
    settings: MediaMopSettings,
    *,
    provider: PrunerProvider,
    display_name: str,
    base_url: str,
    credentials_secrets: dict[str, str],
) -> PrunerServerInstance:
    secrets = envelope_secrets_for_provider(provider, credentials_secrets)
    blob = encrypt_envelope(settings, provider=provider, secrets=secrets)
    normalized = normalize_server_base_url(base_url)
    existing = session.scalars(
        select(PrunerServerInstance).where(
            PrunerServerInstance.provider == provider,
            PrunerServerInstance.normalized_base_url == normalized,
        ),
    ).first()
    if existing is not None:
        msg = "This media server is already configured for Pruner."
        raise ValueError(msg)
    row = PrunerServerInstance(
        provider=provider,
        display_name=display_name.strip(),
        base_url=base_url.strip(),
        normalized_base_url=normalized,
        credentials_ciphertext=blob,
    )
    session.add(row)
    session.flush()
    ensure_scope_rows_for_instance(session, int(row.id))
    session.flush()
    return row


def get_server_instance(session: Session, instance_id: int) -> PrunerServerInstance | None:
    return session.scalars(select(PrunerServerInstance).where(PrunerServerInstance.id == instance_id)).one_or_none()


def get_scope_settings(
    session: Session,
    *,
    server_instance_id: int,
    media_scope: str,
) -> PrunerScopeSettings | None:
    return session.scalars(
        select(PrunerScopeSettings).where(
            PrunerScopeSettings.server_instance_id == server_instance_id,
            PrunerScopeSettings.media_scope == media_scope,
        ),
    ).one_or_none()
