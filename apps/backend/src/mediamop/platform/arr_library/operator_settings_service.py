"""Build API payloads and apply updates for ``arr_library_operator_settings``."""

from __future__ import annotations

from datetime import UTC, datetime, timezone

from sqlalchemy.orm import Session

from mediamop.core.config import MediaMopSettings
from mediamop.platform.arr_library.arr_connection_crypto import encrypt_arr_api_key
from mediamop.platform.arr_library.arr_http_resolve import (
    resolve_radarr_http_credentials,
    resolve_sonarr_http_credentials,
)
from mediamop.platform.arr_library.arr_operator_settings_model import ArrLibraryOperatorSettingsRow
from mediamop.platform.arr_library.arr_operator_settings_repo import ensure_arr_library_operator_settings_row
from mediamop.platform.arr_library.operator_settings_schemas import (
    ArrLibraryConnectionPanelOut,
    ArrLibraryConnectionPutIn,
    ArrLibraryOperatorSettingsOut,
    ArrLibraryOperatorSettingsPutIn,
    ArrLibrarySearchLaneIn,
    ArrLibrarySearchLaneOut,
)
from mediamop.platform.arr_library.schedule_csv_validate import normalize_hhmm, validate_schedule_days_csv
from mediamop.platform.suite_settings.service import ensure_suite_settings_row


def _connection_status_headline(
    *,
    last_ok: bool | None,
    last_at: datetime | None,
    detail: str | None,
) -> str:
    """Single plain-language line for the Connections panel (matches operator mental model)."""

    if last_ok is True:
        return "Connection status: OK"
    if last_at is None and last_ok is None:
        return "Connection status: Not checked yet"
    if last_ok is False:
        d = (detail or "").lower()
        needles = (
            "not set up yet",
            "not set up",
            "did not run",
            "connection is not set up",
            "is not set up yet",
            "library connection check did not run",
        )
        if any(n in d for n in needles):
            return "Connection status: Not set up yet"
        return "Connection status: Failed"
    return "Connection status: Not checked yet"


def _lane_out_from_row(row: ArrLibraryOperatorSettingsRow, prefix: str) -> ArrLibrarySearchLaneOut:
    return ArrLibrarySearchLaneOut(
        enabled=bool(getattr(row, f"{prefix}_enabled")),
        max_items_per_run=int(getattr(row, f"{prefix}_max_items_per_run")),
        retry_delay_minutes=int(getattr(row, f"{prefix}_retry_delay_minutes")),
        schedule_enabled=bool(getattr(row, f"{prefix}_schedule_enabled")),
        schedule_days=(getattr(row, f"{prefix}_schedule_days") or "").strip(),
        schedule_start=(getattr(row, f"{prefix}_schedule_start") or "00:00").strip(),
        schedule_end=(getattr(row, f"{prefix}_schedule_end") or "23:59").strip(),
        schedule_interval_seconds=int(getattr(row, f"{prefix}_schedule_interval_seconds")),
    )


def _sonarr_panel(
    session: Session, settings: MediaMopSettings, row: ArrLibraryOperatorSettingsRow
) -> ArrLibraryConnectionPanelOut:
    eff_b, _eff_k = resolve_sonarr_http_credentials(session, settings)
    return ArrLibraryConnectionPanelOut(
        enabled=bool(row.sonarr_connection_enabled),
        base_url=(row.sonarr_connection_base_url or "").strip(),
        api_key_is_saved=bool((row.sonarr_connection_api_key_ciphertext or "").strip()),
        last_test_ok=row.sonarr_last_connection_test_ok,
        last_test_at=row.sonarr_last_connection_test_at,
        last_test_detail=row.sonarr_last_connection_test_detail,
        status_headline=_connection_status_headline(
            last_ok=row.sonarr_last_connection_test_ok,
            last_at=row.sonarr_last_connection_test_at,
            detail=row.sonarr_last_connection_test_detail,
        ),
        effective_base_url=(eff_b or "").strip() or None,
    )


def _radarr_panel(
    session: Session, settings: MediaMopSettings, row: ArrLibraryOperatorSettingsRow
) -> ArrLibraryConnectionPanelOut:
    eff_b, _eff_k = resolve_radarr_http_credentials(session, settings)
    return ArrLibraryConnectionPanelOut(
        enabled=bool(row.radarr_connection_enabled),
        base_url=(row.radarr_connection_base_url or "").strip(),
        api_key_is_saved=bool((row.radarr_connection_api_key_ciphertext or "").strip()),
        last_test_ok=row.radarr_last_connection_test_ok,
        last_test_at=row.radarr_last_connection_test_at,
        last_test_detail=row.radarr_last_connection_test_detail,
        status_headline=_connection_status_headline(
            last_ok=row.radarr_last_connection_test_ok,
            last_at=row.radarr_last_connection_test_at,
            detail=row.radarr_last_connection_test_detail,
        ),
        effective_base_url=(eff_b or "").strip() or None,
    )


def build_arr_library_operator_settings_out(
    session: Session, settings: MediaMopSettings
) -> ArrLibraryOperatorSettingsOut:
    row = ensure_arr_library_operator_settings_row(session)
    suite_row = ensure_suite_settings_row(session)
    sb, sk = resolve_sonarr_http_credentials(session, settings)
    rb, rk = resolve_radarr_http_credentials(session, settings)
    return ArrLibraryOperatorSettingsOut(
        sonarr_missing=_lane_out_from_row(row, "sonarr_missing_search"),
        sonarr_upgrade=_lane_out_from_row(row, "sonarr_upgrade_search"),
        radarr_missing=_lane_out_from_row(row, "radarr_missing_search"),
        radarr_upgrade=_lane_out_from_row(row, "radarr_upgrade_search"),
        schedule_timezone=(suite_row.app_timezone or "UTC").strip() or "UTC",
        sonarr_connection=_sonarr_panel(session, settings, row),
        radarr_connection=_radarr_panel(session, settings, row),
        connection_note=(
            "When a link is Off, MediaMop does not use that app from this screen or from the server file. "
            "When it is On, saved URL and API keys are encrypted in the database; incomplete settings fall back to the "
            "server file until you save both."
        ),
        interval_restart_note=(
            "If you change how often automatic search checks are queued, restart the MediaMop API so the "
            "background timers pick up the new timing."
        ),
        sonarr_server_configured=bool((sb or "").strip() and (sk or "").strip()),
        radarr_server_configured=bool((rb or "").strip() and (rk or "").strip()),
        sonarr_server_url=(sb or "").strip() or None,
        radarr_server_url=(rb or "").strip() or None,
        updated_at=row.updated_at,
    )


def _apply_lane(row: ArrLibraryOperatorSettingsRow, prefix: str, body: ArrLibrarySearchLaneIn) -> None:
    days = validate_schedule_days_csv(body.schedule_days)
    start = normalize_hhmm(body.schedule_start, fallback="00:00")
    end = normalize_hhmm(body.schedule_end, fallback="23:59")
    setattr(row, f"{prefix}_enabled", bool(body.enabled))
    setattr(row, f"{prefix}_max_items_per_run", int(body.max_items_per_run))
    setattr(row, f"{prefix}_retry_delay_minutes", int(body.retry_delay_minutes))
    setattr(row, f"{prefix}_schedule_enabled", bool(body.schedule_enabled))
    setattr(row, f"{prefix}_schedule_days", days)
    setattr(row, f"{prefix}_schedule_start", start)
    setattr(row, f"{prefix}_schedule_end", end)
    setattr(row, f"{prefix}_schedule_interval_seconds", int(body.schedule_interval_seconds))


_ARR_SEARCH_LANE_ROW_PREFIX: dict[str, str] = {
    "sonarr_missing": "sonarr_missing_search",
    "sonarr_upgrade": "sonarr_upgrade_search",
    "radarr_missing": "radarr_missing_search",
    "radarr_upgrade": "radarr_upgrade_search",
}


def apply_arr_library_operator_settings_lane_put(
    session: Session,
    settings: MediaMopSettings,
    *,
    lane_key: str,
    lane: ArrLibrarySearchLaneIn,
) -> ArrLibraryOperatorSettingsOut:
    """Persist one search lane; other lanes are read from the current row unchanged."""

    prefix = _ARR_SEARCH_LANE_ROW_PREFIX.get(lane_key)
    if prefix is None:
        msg = f"unknown search lane key: {lane_key!r}"
        raise ValueError(msg)
    row = ensure_arr_library_operator_settings_row(session)
    _apply_lane(row, prefix, lane)
    session.flush()
    return build_arr_library_operator_settings_out(session, settings)


def apply_arr_library_operator_settings_put(
    session: Session,
    settings: MediaMopSettings,
    body: ArrLibraryOperatorSettingsPutIn,
) -> ArrLibraryOperatorSettingsOut:
    row = ensure_arr_library_operator_settings_row(session)
    _apply_lane(row, "sonarr_missing_search", body.sonarr_missing)
    _apply_lane(row, "sonarr_upgrade_search", body.sonarr_upgrade)
    _apply_lane(row, "radarr_missing_search", body.radarr_missing)
    _apply_lane(row, "radarr_upgrade_search", body.radarr_upgrade)
    session.flush()
    return build_arr_library_operator_settings_out(session, settings)


def apply_arr_library_connection_put_sonarr(
    session: Session,
    settings: MediaMopSettings,
    body: ArrLibraryConnectionPutIn,
) -> ArrLibraryOperatorSettingsOut:
    row = ensure_arr_library_operator_settings_row(session)
    row.sonarr_connection_enabled = bool(body.enabled)
    row.sonarr_connection_base_url = (body.base_url or "").strip()
    if not row.sonarr_connection_base_url:
        row.sonarr_connection_api_key_ciphertext = None
    elif (body.api_key or "").strip():
        row.sonarr_connection_api_key_ciphertext = encrypt_arr_api_key(settings, body.api_key)
    session.flush()
    return build_arr_library_operator_settings_out(session, settings)


def apply_arr_library_connection_put_radarr(
    session: Session,
    settings: MediaMopSettings,
    body: ArrLibraryConnectionPutIn,
) -> ArrLibraryOperatorSettingsOut:
    row = ensure_arr_library_operator_settings_row(session)
    row.radarr_connection_enabled = bool(body.enabled)
    row.radarr_connection_base_url = (body.base_url or "").strip()
    if not row.radarr_connection_base_url:
        row.radarr_connection_api_key_ciphertext = None
    elif (body.api_key or "").strip():
        row.radarr_connection_api_key_ciphertext = encrypt_arr_api_key(settings, body.api_key)
    session.flush()
    return build_arr_library_operator_settings_out(session, settings)


def record_connection_test_result_sonarr(
    session: Session,
    *,
    ok: bool,
    detail: str,
) -> None:
    row = ensure_arr_library_operator_settings_row(session)
    row.sonarr_last_connection_test_ok = ok
    row.sonarr_last_connection_test_at = datetime.now(UTC)
    row.sonarr_last_connection_test_detail = detail[:2000] if detail else None
    session.flush()


def record_connection_test_result_radarr(
    session: Session,
    *,
    ok: bool,
    detail: str,
) -> None:
    row = ensure_arr_library_operator_settings_row(session)
    row.radarr_last_connection_test_ok = ok
    row.radarr_last_connection_test_at = datetime.now(UTC)
    row.radarr_last_connection_test_detail = detail[:2000] if detail else None
    session.flush()
