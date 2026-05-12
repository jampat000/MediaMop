"""CRUD and helpers for ``subber_providers``."""

from __future__ import annotations

from datetime import UTC, datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from mediamop.core.config import MediaMopSettings
from mediamop.modules.subber.subber_credentials_crypto import (
    build_provider_credentials_plaintext,
    decrypt_subber_credentials_json,
    encrypt_subber_credentials_json,
    parse_provider_secrets_json,
)
from mediamop.modules.subber.subber_provider_registry import (
    ALL_PROVIDER_KEYS,
    PROVIDER_OPENSUBTITLES_COM,
    PROVIDER_OPENSUBTITLES_ORG,
    PROVIDER_REQUIRES_ACCOUNT,
    PROVIDER_SUBDL,
    PROVIDER_SUBSOURCE,
)
from mediamop.modules.subber.subber_providers_model import SubberProviderRow


def ensure_all_provider_rows(session: Session) -> None:
    """Insert missing provider rows (idempotent for DBs pre-dating migration inserts)."""

    existing = set(session.scalars(select(SubberProviderRow.provider_key)).all())
    for pk in ALL_PROVIDER_KEYS:
        if pk in existing:
            continue
        session.add(
            SubberProviderRow(
                provider_key=pk,
                enabled=False,
                priority=None,
                credentials_ciphertext="",
            ),
        )
    session.flush()


def get_all_providers(session: Session) -> list[SubberProviderRow]:
    ensure_all_provider_rows(session)
    return list(
        session.scalars(
            select(SubberProviderRow).order_by(
                SubberProviderRow.priority.asc().nulls_last(),
                SubberProviderRow.id.asc(),
            ),
        ),
    )


def get_enabled_providers_ordered(session: Session) -> list[SubberProviderRow]:
    ensure_all_provider_rows(session)
    return list(
        session.scalars(
            select(SubberProviderRow)
            .where(SubberProviderRow.enabled.is_(True))
            .order_by(
                SubberProviderRow.priority.asc().nulls_last(),
                SubberProviderRow.id.asc(),
            ),
        ).all(),
    )


def get_provider_by_key(session: Session, provider_key: str) -> SubberProviderRow | None:
    ensure_all_provider_rows(session)
    return session.scalars(select(SubberProviderRow).where(SubberProviderRow.provider_key == provider_key)).one_or_none()


def provider_has_stored_credentials(settings: MediaMopSettings, row: SubberProviderRow) -> bool:
    raw = decrypt_subber_credentials_json(settings, row.credentials_ciphertext or "") or ""
    if not raw.strip():
        return False
    sec = parse_provider_secrets_json(row.provider_key, raw)
    if row.provider_key in (PROVIDER_OPENSUBTITLES_ORG, PROVIDER_OPENSUBTITLES_COM):
        return bool(sec.get("username") and sec.get("password") and sec.get("api_key"))
    if row.provider_key in (PROVIDER_SUBDL, PROVIDER_SUBSOURCE):
        return bool(sec.get("api_key"))
    return bool(raw.strip() and raw.strip() != "{}")


def provider_is_ready_for_search(settings: MediaMopSettings, row: SubberProviderRow) -> bool:
    """Whether this enabled provider can participate in a search (anonymous providers ok)."""

    pk = row.provider_key
    if pk in (PROVIDER_OPENSUBTITLES_ORG, PROVIDER_OPENSUBTITLES_COM):
        return provider_has_stored_credentials(settings, row)
    if not PROVIDER_REQUIRES_ACCOUNT.get(pk, True):
        return True
    return provider_has_stored_credentials(settings, row)


def upsert_provider_settings(
    session: Session,
    settings: MediaMopSettings,
    *,
    provider_key: str,
    enabled: bool | None = None,
    priority: int | None = None,
    credentials_secrets: dict[str, str | None] | None = None,
) -> SubberProviderRow:
    ensure_all_provider_rows(session)
    row = get_provider_by_key(session, provider_key)
    if row is None:
        raise ValueError(f"Unknown provider_key {provider_key!r}")
    now = datetime.now(UTC)

    # Auto-assign priority when enabling; clear when disabling
    if enabled is True and row.priority is None:
        from sqlalchemy import func as sa_func
        from sqlalchemy import select as sa_select

        max_priority = session.scalar(
            sa_select(sa_func.max(SubberProviderRow.priority)).where(SubberProviderRow.priority.isnot(None)),
        )
        row.priority = 0 if max_priority is None else int(max_priority) + 1
    elif enabled is False:
        row.priority = None

    if enabled is not None:
        row.enabled = bool(enabled)
    if priority is not None:
        row.priority = int(priority)
    if credentials_secrets is not None:
        plain = build_provider_credentials_plaintext(provider_key, credentials_secrets)
        row.credentials_ciphertext = encrypt_subber_credentials_json(settings, plain)
    row.updated_at = now
    session.flush()
    return row
