"""Per-provider Subber configuration (multi-provider)."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, Field

from mediamop.api.deps import DbSessionDep, SettingsDep
from mediamop.core.config import MediaMopSettings
from mediamop.modules.subber import subber_opensubtitles_client as os_client
from mediamop.modules.subber.subber_credentials_crypto import decrypt_subber_credentials_json, parse_provider_secrets_json
from mediamop.modules.subber.subber_podnapisi_client import LIST_BASE
from mediamop.modules.subber.subber_provider_registry import (
    ALL_PROVIDER_KEYS,
    PROVIDER_ADDIC7ED,
    PROVIDER_AVAILABILITY,
    PROVIDER_DISPLAY_NAMES,
    PROVIDER_OPENSUBTITLES_COM,
    PROVIDER_OPENSUBTITLES_ORG,
    PROVIDER_REQUIRES_ACCOUNT,
)
from mediamop.modules.subber.subber_providers_service import (
    get_all_providers,
    get_provider_by_key,
    provider_has_stored_credentials,
    upsert_provider_settings,
)
from mediamop.modules.subber.subber_schemas import SubberProviderOut, SubberProviderPutIn, SubberTestConnectionOut
from mediamop.platform.outbound_http import validate_external_provider_url
from mediamop.platform.auth.authorization import RequireOperatorDep
from mediamop.platform.auth.csrf import current_raw_session_token, verify_csrf_token

router = APIRouter(tags=["subber-providers"])


class SubberProviderPutHttpIn(SubberProviderPutIn):
    csrf_token: str = Field(..., min_length=1)


class SubberCsrfIn(BaseModel):
    csrf_token: str = Field(..., min_length=1)


def _provider_out(settings: MediaMopSettings, row) -> SubberProviderOut:
    pk = str(row.provider_key)
    available, availability_note = PROVIDER_AVAILABILITY.get(pk, (True, None))
    return SubberProviderOut(
        provider_key=pk,
        display_name=PROVIDER_DISPLAY_NAMES.get(pk, pk),
        enabled=bool(row.enabled),
        priority=int(row.priority) if row.priority is not None else None,
        requires_account=bool(PROVIDER_REQUIRES_ACCOUNT.get(pk, True)),
        has_credentials=provider_has_stored_credentials(settings, row),
        available=available,
        availability_note=availability_note,
    )


@router.get("/providers", response_model=list[SubberProviderOut])
def get_subber_providers(
    _user: RequireOperatorDep,
    db: DbSessionDep,
    settings: SettingsDep,
) -> list[SubberProviderOut]:
    rows = get_all_providers(db)
    order = {k: i for i, k in enumerate(ALL_PROVIDER_KEYS)}
    rows.sort(
        key=lambda r: (
            order.get(str(r.provider_key), 99),
            r.priority if r.priority is not None else 10**6,
            r.id,
        ),
    )
    return [_provider_out(settings, r) for r in rows]


@router.put("/providers/{provider_key}", response_model=SubberProviderOut)
def put_subber_provider(
    _user: RequireOperatorDep,
    db: DbSessionDep,
    request: Request,
    settings: SettingsDep,
    provider_key: str,
    body: SubberProviderPutHttpIn,
) -> SubberProviderOut:
    secret = settings.session_secret or ""
    if not verify_csrf_token(secret, body.csrf_token, raw_session_token=current_raw_session_token(request, settings)):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid CSRF token.")
    pk = provider_key.strip()
    if pk not in ALL_PROVIDER_KEYS:
        raise HTTPException(status_code=404, detail="Unknown provider_key.")
    available, availability_note = PROVIDER_AVAILABILITY.get(pk, (True, None))
    if body.enabled is True and not available:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=availability_note or "Provider is not available in this version.",
        )
    creds: dict[str, str | None] | None = None
    if body.username is not None or (body.password is not None and body.password.strip()) or (
        body.api_key is not None and body.api_key.strip()
    ):
        row0 = get_provider_by_key(db, pk)
        raw_existing = decrypt_subber_credentials_json(settings, row0.credentials_ciphertext or "") if row0 else "{}"
        cur = parse_provider_secrets_json(pk, raw_existing)
        if body.username is not None:
            cur["username"] = body.username.strip()
        if body.password is not None and body.password.strip():
            cur["password"] = body.password
        if body.api_key is not None and body.api_key.strip():
            cur["api_key"] = body.api_key.strip()
        creds = cur
    row = upsert_provider_settings(
        db,
        settings,
        provider_key=pk,
        enabled=body.enabled,
        priority=body.priority,
        credentials_secrets=creds,
    )
    return _provider_out(settings, row)


@router.post("/providers/{provider_key}/test", response_model=SubberTestConnectionOut)
def post_subber_provider_test(
    _user: RequireOperatorDep,
    db: DbSessionDep,
    request: Request,
    settings: SettingsDep,
    provider_key: str,
    body: SubberCsrfIn,
) -> SubberTestConnectionOut:
    secret = settings.session_secret or ""
    if not verify_csrf_token(secret, body.csrf_token, raw_session_token=current_raw_session_token(request, settings)):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid CSRF token.")
    pk = provider_key.strip()
    if pk not in ALL_PROVIDER_KEYS:
        raise HTTPException(status_code=404, detail="Unknown provider_key.")
    rows = get_all_providers(db)
    row = next((r for r in rows if str(r.provider_key) == pk), None)
    if row is None:
        return SubberTestConnectionOut(ok=False, message="Provider row missing.")
    raw = decrypt_subber_credentials_json(settings, row.credentials_ciphertext or "") or "{}"
    sec = parse_provider_secrets_json(pk, raw)
    try:
        if pk in (PROVIDER_OPENSUBTITLES_ORG, PROVIDER_OPENSUBTITLES_COM):
            u, p, k = str(sec.get("username") or ""), str(sec.get("password") or ""), str(sec.get("api_key") or "")
            if not (u and p and k):
                return SubberTestConnectionOut(ok=False, message="Missing username, password, or API key.")
            tok = os_client.login(u, p, k)
            os_client.logout(tok, k)
            return SubberTestConnectionOut(ok=True, message="Connected to OpenSubtitles API.")
        if pk == "podnapisi":
            import urllib.request

            probe_url = validate_external_provider_url(LIST_BASE + "?keywords=test")
            req = urllib.request.Request(  # noqa: S310
                probe_url,
                headers={"User-Agent": "MediaMop/1.0", "Accept": "application/json"},
                method="GET",
            )
            with urllib.request.urlopen(req, timeout=20) as resp:
                code = int(getattr(resp, "status", 200))
            if 200 <= code < 500:
                return SubberTestConnectionOut(ok=True, message="Podnapisi API reachable.")
            return SubberTestConnectionOut(ok=False, message=f"Unexpected HTTP {code}.")
        if pk == "subscene":
            return SubberTestConnectionOut(ok=False, message="Subscene provider not yet implemented.")
        if pk == PROVIDER_ADDIC7ED:
            if not (sec.get("username") and sec.get("password")):
                return SubberTestConnectionOut(ok=False, message="Missing username or password.")
            return SubberTestConnectionOut(ok=False, message="Addic7ed provider not yet implemented.")
    except Exception as exc:
        return SubberTestConnectionOut(ok=False, message=str(exc)[:500])
    return SubberTestConnectionOut(ok=False, message="Unsupported provider.")
