"""HTTP for shared Sonarr/Radarr library preferences (SQLite), connections (SQLite + encrypted keys), and tests."""

from __future__ import annotations

from enum import Enum

from fastapi import APIRouter, HTTPException, Request
from starlette import status

from mediamop.api.deps import DbSessionDep, SettingsDep
from mediamop.core.config import MediaMopSettings
from mediamop.platform.arr_library.arr_http_resolve import (
    preview_radarr_http_credentials_after_put,
    preview_sonarr_http_credentials_after_put,
    resolve_radarr_http_credentials,
    resolve_sonarr_http_credentials,
)
from mediamop.platform.arr_library.operator_settings_schemas import (
    ArrLibraryConnectionPutIn,
    ArrLibraryConnectionTestIn,
    ArrLibraryConnectionTestOut,
    ArrLibraryOperatorSettingsLanePutIn,
    ArrLibraryOperatorSettingsOut,
    ArrLibraryOperatorSettingsPutIn,
)
from mediamop.platform.arr_library.operator_settings_service import (
    apply_arr_library_connection_put_radarr,
    apply_arr_library_connection_put_sonarr,
    apply_arr_library_operator_settings_lane_put,
    apply_arr_library_operator_settings_put,
    build_arr_library_operator_settings_out,
    record_connection_test_result_radarr,
    record_connection_test_result_sonarr,
)
from mediamop.platform.arr_library.arr_v3_http import ArrLibraryV3Client, ArrLibraryV3HttpError
from mediamop.platform.activity import constants as act_c
from mediamop.platform.activity.service import record_activity_event
from mediamop.platform.auth.authorization import RequireOperatorDep
from mediamop.platform.auth.csrf import (
    current_raw_session_token,
    require_session_secret,
    validate_browser_post_origin,
    verify_csrf_token,
)
from mediamop.platform.auth.deps_auth import UserPublicDep

router = APIRouter(tags=["arr-library"])


class ArrSearchLaneKey(str, Enum):
    """URL path keys for single-lane search preference saves."""

    sonarr_missing = "sonarr_missing"
    sonarr_upgrade = "sonarr_upgrade"
    radarr_missing = "radarr_missing"
    radarr_upgrade = "radarr_upgrade"


def _verify_csrf(request: Request, settings: MediaMopSettings, token: str) -> None:
    validate_browser_post_origin(request, settings)
    secret = require_session_secret(settings)
    if not verify_csrf_token(secret, token, raw_session_token=current_raw_session_token(request, settings)):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired CSRF token.",
        )


@router.get(
    "/arr-library/arr-operator-settings",
    response_model=ArrLibraryOperatorSettingsOut,
)
def get_arr_library_operator_settings(
    _user: UserPublicDep,
    db: DbSessionDep,
    settings: SettingsDep,
) -> ArrLibraryOperatorSettingsOut:
    """Shared *arr library: read automatic search lanes and connection panels (saved in this app where applicable)."""

    return build_arr_library_operator_settings_out(db, settings)


@router.put(
    "/arr-library/arr-operator-settings",
    response_model=ArrLibraryOperatorSettingsOut,
)
def put_arr_library_operator_settings(
    body: ArrLibraryOperatorSettingsPutIn,
    request: Request,
    _user: RequireOperatorDep,
    db: DbSessionDep,
    settings: SettingsDep,
) -> ArrLibraryOperatorSettingsOut:
    """Shared *arr library: save automatic search lane preferences (does not change connection fields on this route)."""

    _verify_csrf(request, settings, body.csrf_token)
    try:
        return apply_arr_library_operator_settings_put(db, settings, body)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e) or "Could not save these settings.",
        ) from e


@router.put(
    "/arr-library/arr-operator-settings/lanes/{lane_key}",
    response_model=ArrLibraryOperatorSettingsOut,
)
def put_arr_library_operator_settings_lane(
    lane_key: ArrSearchLaneKey,
    body: ArrLibraryOperatorSettingsLanePutIn,
    request: Request,
    _user: RequireOperatorDep,
    db: DbSessionDep,
    settings: SettingsDep,
) -> ArrLibraryOperatorSettingsOut:
    """Shared *arr library: save one automatic search lane (missing or upgrade for TV or movies)."""

    _verify_csrf(request, settings, body.csrf_token)
    try:
        return apply_arr_library_operator_settings_lane_put(
            db,
            settings,
            lane_key=lane_key.value,
            lane=body.lane,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e) or "Could not save this lane.",
        ) from e


@router.put(
    "/arr-library/arr-connection/sonarr",
    response_model=ArrLibraryOperatorSettingsOut,
)
def put_arr_library_connection_sonarr(
    body: ArrLibraryConnectionPutIn,
    request: Request,
    _user: RequireOperatorDep,
    db: DbSessionDep,
    settings: SettingsDep,
) -> ArrLibraryOperatorSettingsOut:
    _verify_csrf(request, settings, body.csrf_token)
    try:
        return apply_arr_library_connection_put_sonarr(db, settings, body)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e) or "Could not save TV library connection.",
        ) from e


@router.put(
    "/arr-library/arr-connection/radarr",
    response_model=ArrLibraryOperatorSettingsOut,
)
def put_arr_library_connection_radarr(
    body: ArrLibraryConnectionPutIn,
    request: Request,
    _user: RequireOperatorDep,
    db: DbSessionDep,
    settings: SettingsDep,
) -> ArrLibraryOperatorSettingsOut:
    _verify_csrf(request, settings, body.csrf_token)
    try:
        return apply_arr_library_connection_put_radarr(db, settings, body)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e) or "Could not save movie library connection.",
        ) from e


@router.post(
    "/arr-library/arr-operator-settings/connection-test",
    response_model=ArrLibraryConnectionTestOut,
)
def post_arr_library_connection_test(
    body: ArrLibraryConnectionTestIn,
    request: Request,
    _user: RequireOperatorDep,
    db: DbSessionDep,
    settings: SettingsDep,
) -> ArrLibraryConnectionTestOut:
    """Try a reachability check to Sonarr or Radarr; outcome is saved on Activity and on the settings row.

    When ``enabled`` is present, ``base_url`` and ``api_key`` are interpreted like ``PUT …/arr-connection/*`` (draft
    test without saving). When ``enabled`` is omitted, credentials come only from stored settings and the server file.
    """

    _verify_csrf(request, settings, body.csrf_token)
    app = (body.app or "").strip().lower()
    if app not in ("sonarr", "radarr"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Choose Sonarr or Radarr.",
        )

    if app == "sonarr":
        if body.enabled is not None:
            bu = "" if body.base_url is None else body.base_url
            ak = "" if body.api_key is None else body.api_key
            base, key = preview_sonarr_http_credentials_after_put(
                db,
                settings,
                enabled=body.enabled,
                base_url=bu,
                api_key=ak,
            )
        else:
            base, key = resolve_sonarr_http_credentials(db, settings)
        configured = bool((base or "").strip() and (key or "").strip())
        if not configured:
            detail = (
                "TV library connection is not set up yet. Turn the connection on, enter an address and API key here, "
                "or add them to the MediaMop server configuration file."
            )
            record_activity_event(
                db,
                event_type=act_c.ARR_LIBRARY_CONNECTION_TEST_FAILED,
                module="arr_library",
                title="TV library connection check did not run",
                detail=detail,
            )
            record_connection_test_result_sonarr(db, ok=False, detail=detail)
            return ArrLibraryConnectionTestOut(ok=False, message=detail)
        try:
            ArrLibraryV3Client(base.strip(), key.strip()).health_ok()
        except ArrLibraryV3HttpError as e:
            msg = (
                "MediaMop could reach your TV library app, but it did not accept the request. "
                "Check the address, API key, and that the app is running."
            )
            record_activity_event(
                db,
                event_type=act_c.ARR_LIBRARY_CONNECTION_TEST_FAILED,
                module="arr_library",
                title="TV library connection check failed",
                detail=f"{msg} ({e})",
            )
            record_connection_test_result_sonarr(db, ok=False, detail=msg)
            return ArrLibraryConnectionTestOut(ok=False, message=msg)
        except OSError as e:
            msg = "MediaMop could not open a network connection to your TV library app. Check the address and network."
            record_activity_event(
                db,
                event_type=act_c.ARR_LIBRARY_CONNECTION_TEST_FAILED,
                module="arr_library",
                title="TV library connection check failed",
                detail=f"{msg} ({e})",
            )
            record_connection_test_result_sonarr(db, ok=False, detail=msg)
            return ArrLibraryConnectionTestOut(ok=False, message=msg)

        ok_detail = "MediaMop reached your TV library app and received a normal response."
        record_activity_event(
            db,
            event_type=act_c.ARR_LIBRARY_CONNECTION_TEST_SUCCEEDED,
            module="arr_library",
            title="TV library connection check succeeded",
            detail=ok_detail,
        )
        record_connection_test_result_sonarr(db, ok=True, detail="Connection status: OK")
        return ArrLibraryConnectionTestOut(
            ok=True,
            message="Connection looks good. This was a one-time check — it is not continuous monitoring.",
        )

    if body.enabled is not None:
        bu = "" if body.base_url is None else body.base_url
        ak = "" if body.api_key is None else body.api_key
        base, key = preview_radarr_http_credentials_after_put(
            db,
            settings,
            enabled=body.enabled,
            base_url=bu,
            api_key=ak,
        )
    else:
        base, key = resolve_radarr_http_credentials(db, settings)
    configured = bool((base or "").strip() and (key or "").strip())
    if not configured:
        detail = (
            "Movie library connection is not set up yet. Turn the connection on, enter an address and API key here, "
            "or add them to the MediaMop server configuration file."
        )
        record_activity_event(
            db,
            event_type=act_c.ARR_LIBRARY_CONNECTION_TEST_FAILED,
            module="arr_library",
            title="Movie library connection check did not run",
            detail=detail,
        )
        record_connection_test_result_radarr(db, ok=False, detail=detail)
        return ArrLibraryConnectionTestOut(ok=False, message=detail)
    try:
        ArrLibraryV3Client(base.strip(), key.strip()).health_ok()
    except ArrLibraryV3HttpError as e:
        msg = (
            "MediaMop could reach your movie library app, but it did not accept the request. "
            "Check the address, API key, and that the app is running."
        )
        record_activity_event(
            db,
            event_type=act_c.ARR_LIBRARY_CONNECTION_TEST_FAILED,
            module="arr_library",
            title="Movie library connection check failed",
            detail=f"{msg} ({e})",
        )
        record_connection_test_result_radarr(db, ok=False, detail=msg)
        return ArrLibraryConnectionTestOut(ok=False, message=msg)
    except OSError as e:
        msg = "MediaMop could not open a network connection to your movie library app. Check the address and network."
        record_activity_event(
            db,
            event_type=act_c.ARR_LIBRARY_CONNECTION_TEST_FAILED,
            module="arr_library",
            title="Movie library connection check failed",
            detail=f"{msg} ({e})",
        )
        record_connection_test_result_radarr(db, ok=False, detail=msg)
        return ArrLibraryConnectionTestOut(ok=False, message=msg)

    ok_detail = "MediaMop reached your movie library app and received a normal response."
    record_activity_event(
        db,
        event_type=act_c.ARR_LIBRARY_CONNECTION_TEST_SUCCEEDED,
        module="arr_library",
        title="Movie library connection check succeeded",
        detail=ok_detail,
    )
    record_connection_test_result_radarr(db, ok=True, detail="Connection status: OK")
    return ArrLibraryConnectionTestOut(
        ok=True,
        message="Connection looks good. This was a one-time check — it is not continuous monitoring.",
    )
