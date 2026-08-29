"""Refiner HTTP: the metadata provider connection — ``/api/v1/refiner/metadata-provider``.

The key is write-only. It is stored encrypted and never returned, so a screen can report
that one is configured without ever being able to leak it.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from starlette import status as http_status

from mediamop.api.deps import DbSessionDep, SettingsDep
from mediamop.core.config import MediaMopSettings
from mediamop.integrations.metadata.provider_service import KNOWN_PROVIDERS, store_provider_key, test_provider
from mediamop.integrations.metadata.tmdb_provider import DEFAULT_TMDB_BASE_URL, clear_metadata_cache
from mediamop.modules.refiner.schemas_refiner_metadata_provider import (
    MetadataProviderIn,
    MetadataProviderOut,
    MetadataProviderTestOut,
)
from mediamop.platform.auth.authorization import RequireOperatorDep
from mediamop.platform.auth.csrf import (
    current_raw_session_token,
    require_session_secret,
    validate_browser_post_origin,
    verify_csrf_token,
)
from mediamop.platform.auth.deps_auth import UserPublicDep
from mediamop.platform.suite_settings.model import SuiteSettingsRow
from mediamop.platform.suite_settings.service import ensure_suite_settings_row

router = APIRouter(tags=["refiner"])


def _verify_csrf(request: Request, settings: MediaMopSettings, token: str) -> None:
    validate_browser_post_origin(request, settings)
    secret = require_session_secret(settings)
    if not verify_csrf_token(secret, token, raw_session_token=current_raw_session_token(request, settings)):
        raise HTTPException(status_code=http_status.HTTP_400_BAD_REQUEST, detail="Invalid or expired CSRF token.")


def _out(row: SuiteSettingsRow) -> MetadataProviderOut:
    return MetadataProviderOut(
        provider=row.metadata_provider or "",
        base_url=(row.metadata_provider_base_url or "").strip() or DEFAULT_TMDB_BASE_URL,
        key_configured=bool((row.metadata_provider_key_ciphertext or "").strip()),
        known_providers=list(KNOWN_PROVIDERS),
    )


@router.get("/refiner/metadata-provider", response_model=MetadataProviderOut)
def get_metadata_provider(_user: UserPublicDep, db: DbSessionDep) -> MetadataProviderOut:
    row = ensure_suite_settings_row(db)
    db.commit()
    return _out(row)


@router.put("/refiner/metadata-provider", response_model=MetadataProviderOut)
def put_metadata_provider(
    request: Request,
    _operator: RequireOperatorDep,
    db: DbSessionDep,
    settings: SettingsDep,
    body: MetadataProviderIn,
) -> MetadataProviderOut:
    _verify_csrf(request, settings, body.csrf_token)
    row = ensure_suite_settings_row(db)
    row.metadata_provider = body.provider
    row.metadata_provider_base_url = body.base_url.strip()
    if body.api_key is not None:
        # Omitting it leaves the stored key alone, so saving the base URL does not require
        # re-typing a secret the screen cannot show back.
        row.metadata_provider_key_ciphertext = store_provider_key(settings, body.api_key)
    db.flush()
    db.commit()
    # Cached answers were fetched with the old credentials or from the old address.
    clear_metadata_cache()
    return _out(row)


@router.post("/refiner/metadata-provider/test", response_model=MetadataProviderTestOut)
def post_metadata_provider_test(
    request: Request,
    _operator: RequireOperatorDep,
    db: DbSessionDep,
    settings: SettingsDep,
    body: MetadataProviderIn,
) -> MetadataProviderTestOut:
    """Ask the provider a real question, so a saved connection is proven rather than assumed."""

    _verify_csrf(request, settings, body.csrf_token)
    result = test_provider(db, settings)
    db.commit()
    return MetadataProviderTestOut(status=result.status, detail=result.detail)
