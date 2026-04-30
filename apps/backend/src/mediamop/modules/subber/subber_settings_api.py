"""Subber singleton settings + connection tests."""

from __future__ import annotations

import json
import uuid
import urllib.error
import urllib.request
from typing import Annotated

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, Field

from mediamop.api.deps import DbSessionDep, SettingsDep
from mediamop.core.config import MediaMopSettings
from mediamop.modules.subber.subber_credentials_crypto import decrypt_subber_credentials_json, encrypt_subber_credentials_json
from mediamop.modules.subber.subber_job_kinds import SUBBER_JOB_KIND_LIBRARY_SYNC_MOVIES, SUBBER_JOB_KIND_LIBRARY_SYNC_TV
from mediamop.modules.subber.subber_jobs_ops import subber_enqueue_or_get_job
from mediamop.modules.subber.subber_opensubtitles_client import USER_AGENT
from mediamop.modules.subber import subber_opensubtitles_client as os_client
from mediamop.modules.subber.subber_overview_service import build_subber_overview
from mediamop.modules.subber.subber_schemas import (
    SubberArrRootFolderOut,
    SubberArrRootFoldersOut,
    SubberOverviewOut,
    SubberSettingsOut,
    SubberSettingsPutIn,
    SubberTestConnectionOut,
)
from mediamop.modules.subber.subber_settings_model import SubberSettingsRow
from mediamop.modules.subber.subber_settings_service import (
    ensure_subber_settings_row,
    get_arr_library_connection_hints,
    language_preferences_list,
    set_language_preferences_json,
)
from mediamop.platform.auth.authorization import RequireOperatorDep
from mediamop.platform.auth.csrf import current_raw_session_token, verify_csrf_token

router = APIRouter(tags=["subber-settings"])


def _masked_set(ciphertext: str | None) -> bool:
    return bool((ciphertext or "").strip())


def _settings_out(db, row: SubberSettingsRow, request: Request, settings: MediaMopSettings) -> SubberSettingsOut:
    son_hint, rad_hint = get_arr_library_connection_hints(db)
    _ = request, settings
    return SubberSettingsOut(
        enabled=bool(row.enabled),
        opensubtitles_username=str(row.opensubtitles_username or ""),
        opensubtitles_password_set=_masked_set(row.opensubtitles_credentials_ciphertext),
        opensubtitles_api_key_set=_masked_set(row.opensubtitles_credentials_ciphertext),
        sonarr_base_url=str(row.sonarr_base_url or ""),
        sonarr_api_key_set=_masked_set(row.sonarr_credentials_ciphertext),
        radarr_base_url=str(row.radarr_base_url or ""),
        radarr_api_key_set=_masked_set(row.radarr_credentials_ciphertext),
        language_preferences=language_preferences_list(row),
        subtitle_folder=str(row.subtitle_folder or ""),
        tv_schedule_enabled=bool(row.tv_schedule_enabled),
        tv_schedule_interval_seconds=int(row.tv_schedule_interval_seconds),
        tv_schedule_hours_limited=bool(row.tv_schedule_hours_limited),
        tv_schedule_days=str(row.tv_schedule_days or ""),
        tv_schedule_start=str(row.tv_schedule_start or "00:00"),
        tv_schedule_end=str(row.tv_schedule_end or "23:59"),
        movies_schedule_enabled=bool(row.movies_schedule_enabled),
        movies_schedule_interval_seconds=int(row.movies_schedule_interval_seconds),
        movies_schedule_hours_limited=bool(row.movies_schedule_hours_limited),
        movies_schedule_days=str(row.movies_schedule_days or ""),
        movies_schedule_start=str(row.movies_schedule_start or "00:00"),
        movies_schedule_end=str(row.movies_schedule_end or "23:59"),
        tv_last_scheduled_scan_enqueued_at=row.tv_last_scheduled_scan_enqueued_at,
        movies_last_scheduled_scan_enqueued_at=row.movies_last_scheduled_scan_enqueued_at,
        adaptive_searching_enabled=bool(row.adaptive_searching_enabled),
        adaptive_searching_delay_hours=int(row.adaptive_searching_delay_hours or 168),
        adaptive_searching_max_attempts=int(row.adaptive_searching_max_attempts or 3),
        permanent_skip_after_attempts=int(row.permanent_skip_after_attempts or 10),
        exclude_hearing_impaired=bool(row.exclude_hearing_impaired),
        upgrade_enabled=bool(row.upgrade_enabled),
        upgrade_schedule_enabled=bool(row.upgrade_schedule_enabled),
        upgrade_schedule_interval_seconds=int(row.upgrade_schedule_interval_seconds or 604800),
        upgrade_schedule_hours_limited=bool(row.upgrade_schedule_hours_limited),
        upgrade_schedule_days=str(row.upgrade_schedule_days or ""),
        upgrade_schedule_start=str(row.upgrade_schedule_start or "00:00"),
        upgrade_schedule_end=str(row.upgrade_schedule_end or "23:59"),
        upgrade_last_scheduled_at=row.upgrade_last_scheduled_at,
        sonarr_path_mapping_enabled=bool(row.sonarr_path_mapping_enabled),
        sonarr_path_sonarr=str(row.sonarr_path_sonarr or ""),
        sonarr_path_subber=str(row.sonarr_path_subber or ""),
        radarr_path_mapping_enabled=bool(row.radarr_path_mapping_enabled),
        radarr_path_radarr=str(row.radarr_path_radarr or ""),
        radarr_path_subber=str(row.radarr_path_subber or ""),
        arr_library_sonarr_base_url_hint=son_hint,
        arr_library_radarr_base_url_hint=rad_hint,
    )


class SubberSettingsPutHttpIn(SubberSettingsPutIn):
    csrf_token: str = Field(..., min_length=1)


class SubberCsrfIn(BaseModel):
    csrf_token: str = Field(..., min_length=1)


@router.get("/settings", response_model=SubberSettingsOut)
def get_subber_settings(
    _user: RequireOperatorDep,
    db: DbSessionDep,
    request: Request,
    settings: SettingsDep,
) -> SubberSettingsOut:
    row = ensure_subber_settings_row(db)
    return _settings_out(db, row, request, settings)


@router.put("/settings", response_model=SubberSettingsOut)
def put_subber_settings(
    _user: RequireOperatorDep,
    db: DbSessionDep,
    request: Request,
    settings: SettingsDep,
    body: SubberSettingsPutHttpIn,
) -> SubberSettingsOut:
    secret = settings.session_secret or ""
    if not verify_csrf_token(secret, body.csrf_token, raw_session_token=current_raw_session_token(request, settings)):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid CSRF token.")
    row = ensure_subber_settings_row(db)
    if body.enabled is not None:
        row.enabled = bool(body.enabled)
    if body.opensubtitles_username is not None:
        row.opensubtitles_username = body.opensubtitles_username.strip()
        raw_u = decrypt_subber_credentials_json(settings, row.opensubtitles_credentials_ciphertext or "") or "{}"
        try:
            cur_u = json.loads(raw_u)
        except json.JSONDecodeError:
            cur_u = {"provider": "opensubtitles", "secrets": {}}
        if not isinstance(cur_u, dict):
            cur_u = {"provider": "opensubtitles", "secrets": {}}
        sec_u = cur_u.get("secrets") if isinstance(cur_u.get("secrets"), dict) else {}
        sec_u["username"] = row.opensubtitles_username
        cur_u["provider"] = "opensubtitles"
        cur_u["secrets"] = sec_u
        row.opensubtitles_credentials_ciphertext = encrypt_subber_credentials_json(settings, json.dumps(cur_u))
    if body.opensubtitles_password is not None and body.opensubtitles_password.strip():
        raw = decrypt_subber_credentials_json(settings, row.opensubtitles_credentials_ciphertext or "") or "{}"
        try:
            cur = json.loads(raw)
        except json.JSONDecodeError:
            cur = {"provider": "opensubtitles", "secrets": {}}
        if not isinstance(cur, dict):
            cur = {"provider": "opensubtitles", "secrets": {}}
        sec = cur.get("secrets") if isinstance(cur.get("secrets"), dict) else {}
        sec["password"] = body.opensubtitles_password
        cur["provider"] = "opensubtitles"
        cur["secrets"] = sec
        row.opensubtitles_credentials_ciphertext = encrypt_subber_credentials_json(settings, json.dumps(cur))
    if body.opensubtitles_api_key is not None and body.opensubtitles_api_key.strip():
        raw = decrypt_subber_credentials_json(settings, row.opensubtitles_credentials_ciphertext or "") or "{}"
        try:
            cur = json.loads(raw)
        except json.JSONDecodeError:
            cur = {"provider": "opensubtitles", "secrets": {}}
        if not isinstance(cur, dict):
            cur = {"provider": "opensubtitles", "secrets": {}}
        sec = cur.get("secrets") if isinstance(cur.get("secrets"), dict) else {}
        sec["api_key"] = body.opensubtitles_api_key.strip()
        cur["provider"] = "opensubtitles"
        cur["secrets"] = sec
        row.opensubtitles_credentials_ciphertext = encrypt_subber_credentials_json(settings, json.dumps(cur))
    if body.sonarr_base_url is not None:
        row.sonarr_base_url = body.sonarr_base_url.strip()
    if body.sonarr_api_key is not None and body.sonarr_api_key.strip():
        env = json.dumps({"provider": "sonarr", "secrets": {"api_key": body.sonarr_api_key.strip()}})
        row.sonarr_credentials_ciphertext = encrypt_subber_credentials_json(settings, env)
    if body.radarr_base_url is not None:
        row.radarr_base_url = body.radarr_base_url.strip()
    if body.radarr_api_key is not None and body.radarr_api_key.strip():
        env = json.dumps({"provider": "radarr", "secrets": {"api_key": body.radarr_api_key.strip()}})
        row.radarr_credentials_ciphertext = encrypt_subber_credentials_json(settings, env)
    if body.language_preferences is not None:
        set_language_preferences_json(db, row, body.language_preferences)
    if body.subtitle_folder is not None:
        row.subtitle_folder = body.subtitle_folder.strip()
    _apply_sched(row, body)
    _apply_extended_settings(row, body)
    db.flush()

    def _api_key_from_ciphertext(ct: str | None) -> str:
        raw = decrypt_subber_credentials_json(settings, ct or "") or "{}"
        try:
            kd = json.loads(raw)
        except json.JSONDecodeError:
            kd = {}
        sec = kd.get("secrets") if isinstance(kd.get("secrets"), dict) else {}
        return str(sec.get("api_key") or "").strip()

    son_key = _api_key_from_ciphertext(row.sonarr_credentials_ciphertext)
    rad_key = _api_key_from_ciphertext(row.radarr_credentials_ciphertext)
    son_configured = bool((row.sonarr_base_url or "").strip()) and bool(son_key)
    rad_configured = bool((row.radarr_base_url or "").strip()) and bool(rad_key)
    if body.sonarr_base_url is not None or (body.sonarr_api_key is not None and body.sonarr_api_key.strip()):
        if son_configured:
            subber_enqueue_or_get_job(
                db,
                dedupe_key=f"subber:libsync:settings:tv:{uuid.uuid4()}",
                job_kind=SUBBER_JOB_KIND_LIBRARY_SYNC_TV,
                payload_json="{}",
            )
    if body.radarr_base_url is not None or (body.radarr_api_key is not None and body.radarr_api_key.strip()):
        if rad_configured:
            subber_enqueue_or_get_job(
                db,
                dedupe_key=f"subber:libsync:settings:movies:{uuid.uuid4()}",
                job_kind=SUBBER_JOB_KIND_LIBRARY_SYNC_MOVIES,
                payload_json="{}",
            )

    return _settings_out(db, row, request, settings)


def _apply_extended_settings(row: SubberSettingsRow, body: SubberSettingsPutIn) -> None:
    if body.adaptive_searching_enabled is not None:
        row.adaptive_searching_enabled = bool(body.adaptive_searching_enabled)
    if body.adaptive_searching_delay_hours is not None:
        row.adaptive_searching_delay_hours = int(body.adaptive_searching_delay_hours)
    if body.adaptive_searching_max_attempts is not None:
        row.adaptive_searching_max_attempts = int(body.adaptive_searching_max_attempts)
    if body.permanent_skip_after_attempts is not None:
        row.permanent_skip_after_attempts = int(body.permanent_skip_after_attempts)
    if body.exclude_hearing_impaired is not None:
        row.exclude_hearing_impaired = bool(body.exclude_hearing_impaired)
    if body.upgrade_enabled is not None:
        row.upgrade_enabled = bool(body.upgrade_enabled)
    if body.upgrade_schedule_enabled is not None:
        row.upgrade_schedule_enabled = bool(body.upgrade_schedule_enabled)
    if body.upgrade_schedule_interval_seconds is not None:
        row.upgrade_schedule_interval_seconds = int(body.upgrade_schedule_interval_seconds)
    if body.upgrade_schedule_hours_limited is not None:
        row.upgrade_schedule_hours_limited = bool(body.upgrade_schedule_hours_limited)
    if body.upgrade_schedule_days is not None:
        row.upgrade_schedule_days = body.upgrade_schedule_days.strip()
    if body.upgrade_schedule_start is not None:
        row.upgrade_schedule_start = body.upgrade_schedule_start.strip()
    if body.upgrade_schedule_end is not None:
        row.upgrade_schedule_end = body.upgrade_schedule_end.strip()
    if body.sonarr_path_mapping_enabled is not None:
        row.sonarr_path_mapping_enabled = bool(body.sonarr_path_mapping_enabled)
    if body.sonarr_path_sonarr is not None:
        row.sonarr_path_sonarr = body.sonarr_path_sonarr.strip()
    if body.sonarr_path_subber is not None:
        row.sonarr_path_subber = body.sonarr_path_subber.strip()
    if body.radarr_path_mapping_enabled is not None:
        row.radarr_path_mapping_enabled = bool(body.radarr_path_mapping_enabled)
    if body.radarr_path_radarr is not None:
        row.radarr_path_radarr = body.radarr_path_radarr.strip()
    if body.radarr_path_subber is not None:
        row.radarr_path_subber = body.radarr_path_subber.strip()


def _apply_sched(row: SubberSettingsRow, body: SubberSettingsPutIn) -> None:
    if body.tv_schedule_enabled is not None:
        row.tv_schedule_enabled = bool(body.tv_schedule_enabled)
    if body.tv_schedule_interval_seconds is not None:
        row.tv_schedule_interval_seconds = int(body.tv_schedule_interval_seconds)
    if body.tv_schedule_hours_limited is not None:
        row.tv_schedule_hours_limited = bool(body.tv_schedule_hours_limited)
    if body.tv_schedule_days is not None:
        row.tv_schedule_days = body.tv_schedule_days.strip()
    if body.tv_schedule_start is not None:
        row.tv_schedule_start = body.tv_schedule_start.strip()
    if body.tv_schedule_end is not None:
        row.tv_schedule_end = body.tv_schedule_end.strip()
    if body.movies_schedule_enabled is not None:
        row.movies_schedule_enabled = bool(body.movies_schedule_enabled)
    if body.movies_schedule_interval_seconds is not None:
        row.movies_schedule_interval_seconds = int(body.movies_schedule_interval_seconds)
    if body.movies_schedule_hours_limited is not None:
        row.movies_schedule_hours_limited = bool(body.movies_schedule_hours_limited)
    if body.movies_schedule_days is not None:
        row.movies_schedule_days = body.movies_schedule_days.strip()
    if body.movies_schedule_start is not None:
        row.movies_schedule_start = body.movies_schedule_start.strip()
    if body.movies_schedule_end is not None:
        row.movies_schedule_end = body.movies_schedule_end.strip()


@router.post("/settings/test-opensubtitles", response_model=SubberTestConnectionOut)
def post_test_opensubtitles(
    _user: RequireOperatorDep,
    db: DbSessionDep,
    request: Request,
    settings: SettingsDep,
    body: SubberCsrfIn,
) -> SubberTestConnectionOut:
    secret = settings.session_secret or ""
    if not verify_csrf_token(secret, body.csrf_token, raw_session_token=current_raw_session_token(request, settings)):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid CSRF token.")
    row = ensure_subber_settings_row(db)
    raw = decrypt_subber_credentials_json(settings, row.opensubtitles_credentials_ciphertext or "") or "{}"
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return SubberTestConnectionOut(ok=False, message="Credentials not configured.")
    sec = data.get("secrets") if isinstance(data.get("secrets"), dict) else {}
    u, p, k = (
        str(sec.get("username") or "").strip(),
        str(sec.get("password") or "").strip(),
        str(sec.get("api_key") or "").strip(),
    )
    if not (u and p and k):
        return SubberTestConnectionOut(ok=False, message="Missing username, password, or API key.")
    try:
        tok = os_client.login(u, p, k)
        info = os_client.fetch_user_info(tok, k)
        os_client.logout(tok, k)
        remaining = ""
        if isinstance(info, dict):
            rem = info.get("remaining") or info.get("downloads_remaining")
            if rem is not None:
                remaining = f" Remaining quota: {rem}."
        return SubberTestConnectionOut(ok=True, message=f"Connected.{remaining}".strip())
    except Exception as exc:
        return SubberTestConnectionOut(ok=False, message=str(exc)[:500])


def _arr_status_probe(base_url: str, api_key: str) -> tuple[bool, str]:
    u = base_url.rstrip("/") + "/api/v3/system/status"
    req = urllib.request.Request(  # noqa: S310
        u,
        headers={"X-Api-Key": api_key, "User-Agent": USER_AGENT},
        method="GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            code = int(getattr(resp, "status", 200))
            if 200 <= code < 300:
                return True, "OK"
            return False, f"HTTP {code}"
    except urllib.error.HTTPError as e:
        return False, f"HTTP {e.code}"
    except Exception as exc:
        return False, str(exc)[:500]


def _arr_api_key(settings: MediaMopSettings, ciphertext: str | None) -> str:
    raw = decrypt_subber_credentials_json(settings, ciphertext or "") or "{}"
    try:
        kd = json.loads(raw)
    except json.JSONDecodeError:
        kd = {}
    sec = kd.get("secrets") if isinstance(kd.get("secrets"), dict) else {}
    return str(sec.get("api_key") or "").strip()


def _arr_root_folders(base_url: str, api_key: str) -> tuple[bool, str, list[SubberArrRootFolderOut]]:
    u = base_url.rstrip("/") + "/api/v3/rootfolder"
    req = urllib.request.Request(  # noqa: S310
        u,
        headers={"X-Api-Key": api_key, "User-Agent": USER_AGENT},
        method="GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            code = int(getattr(resp, "status", 200))
            if not (200 <= code < 300):
                return False, f"HTTP {code}", []
            payload = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return False, f"HTTP {e.code}", []
    except json.JSONDecodeError:
        return False, "The server returned invalid JSON.", []
    except Exception as exc:
        return False, str(exc)[:500], []
    if not isinstance(payload, list):
        return False, "The server did not return a folder list.", []
    folders: list[SubberArrRootFolderOut] = []
    seen: set[str] = set()
    for item in payload:
        if not isinstance(item, dict):
            continue
        path = str(item.get("path") or "").strip()
        if not path or path in seen:
            continue
        free_raw = item.get("freeSpace", item.get("freeSpaceBytes"))
        free_space = int(free_raw) if isinstance(free_raw, int) else None
        folders.append(SubberArrRootFolderOut(path=path, free_space=free_space))
        seen.add(path)
    return True, f"Found {len(folders)} root folder{'s' if len(folders) != 1 else ''}.", folders


@router.post("/settings/test-sonarr", response_model=SubberTestConnectionOut)
def post_test_sonarr(
    _user: RequireOperatorDep,
    db: DbSessionDep,
    request: Request,
    settings: SettingsDep,
    body: SubberCsrfIn,
) -> SubberTestConnectionOut:
    secret = settings.session_secret or ""
    if not verify_csrf_token(secret, body.csrf_token, raw_session_token=current_raw_session_token(request, settings)):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid CSRF token.")
    row = ensure_subber_settings_row(db)
    key_raw = decrypt_subber_credentials_json(settings, row.sonarr_credentials_ciphertext or "") or "{}"
    try:
        kd = json.loads(key_raw)
    except json.JSONDecodeError:
        kd = {}
    sec = kd.get("secrets") if isinstance(kd.get("secrets"), dict) else {}
    api_key = str(sec.get("api_key") or "").strip()
    if not row.sonarr_base_url.strip() or not api_key:
        return SubberTestConnectionOut(ok=False, message="Sonarr URL or API key not set.")
    ok, msg = _arr_status_probe(row.sonarr_base_url, api_key)
    return SubberTestConnectionOut(ok=ok, message=msg)


@router.post("/settings/sonarr-root-folders", response_model=SubberArrRootFoldersOut)
def post_sonarr_root_folders(
    _user: RequireOperatorDep,
    db: DbSessionDep,
    request: Request,
    settings: SettingsDep,
    body: SubberCsrfIn,
) -> SubberArrRootFoldersOut:
    secret = settings.session_secret or ""
    if not verify_csrf_token(secret, body.csrf_token, raw_session_token=current_raw_session_token(request, settings)):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid CSRF token.")
    row = ensure_subber_settings_row(db)
    api_key = _arr_api_key(settings, row.sonarr_credentials_ciphertext)
    if not row.sonarr_base_url.strip() or not api_key:
        return SubberArrRootFoldersOut(ok=False, message="Save the Sonarr URL and API key first.")
    ok, msg, folders = _arr_root_folders(row.sonarr_base_url, api_key)
    return SubberArrRootFoldersOut(ok=ok, message=msg, folders=folders)


@router.post("/settings/test-radarr", response_model=SubberTestConnectionOut)
def post_test_radarr(
    _user: RequireOperatorDep,
    db: DbSessionDep,
    request: Request,
    settings: SettingsDep,
    body: SubberCsrfIn,
) -> SubberTestConnectionOut:
    secret = settings.session_secret or ""
    if not verify_csrf_token(secret, body.csrf_token, raw_session_token=current_raw_session_token(request, settings)):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid CSRF token.")
    row = ensure_subber_settings_row(db)
    key_raw = decrypt_subber_credentials_json(settings, row.radarr_credentials_ciphertext or "") or "{}"
    try:
        kd = json.loads(key_raw)
    except json.JSONDecodeError:
        kd = {}
    sec = kd.get("secrets") if isinstance(kd.get("secrets"), dict) else {}
    api_key = str(sec.get("api_key") or "").strip()
    if not row.radarr_base_url.strip() or not api_key:
        return SubberTestConnectionOut(ok=False, message="Radarr URL or API key not set.")
    ok, msg = _arr_status_probe(row.radarr_base_url, api_key)
    return SubberTestConnectionOut(ok=ok, message=msg)


@router.post("/settings/radarr-root-folders", response_model=SubberArrRootFoldersOut)
def post_radarr_root_folders(
    _user: RequireOperatorDep,
    db: DbSessionDep,
    request: Request,
    settings: SettingsDep,
    body: SubberCsrfIn,
) -> SubberArrRootFoldersOut:
    secret = settings.session_secret or ""
    if not verify_csrf_token(secret, body.csrf_token, raw_session_token=current_raw_session_token(request, settings)):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid CSRF token.")
    row = ensure_subber_settings_row(db)
    api_key = _arr_api_key(settings, row.radarr_credentials_ciphertext)
    if not row.radarr_base_url.strip() or not api_key:
        return SubberArrRootFoldersOut(ok=False, message="Save the Radarr URL and API key first.")
    ok, msg, folders = _arr_root_folders(row.radarr_base_url, api_key)
    return SubberArrRootFoldersOut(ok=ok, message=msg, folders=folders)


@router.get("/overview", response_model=SubberOverviewOut)
def get_subber_overview(
    _user: RequireOperatorDep,
    db: DbSessionDep,
) -> SubberOverviewOut:
    return build_subber_overview(db)
