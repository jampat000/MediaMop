"""Search and download subtitles (multi-provider + legacy OpenSubtitles settings)."""

from __future__ import annotations

import io
import json
import logging
import re
import zipfile
from pathlib import Path

from sqlalchemy.orm import Session

from mediamop.core.config import MediaMopSettings
from mediamop.modules.subber import subber_addic7ed_client as addic7ed_client
from mediamop.modules.subber import subber_gestdown_client as gestdown_client
from mediamop.modules.subber import subber_opensubtitles_client as os_client
from mediamop.modules.subber import subber_podnapisi_client as podnapisi_client
from mediamop.modules.subber import subber_subdl_client as subdl_client
from mediamop.modules.subber import subber_subf2m_client as subf2m_client
from mediamop.modules.subber import subber_subscene_client as subscene_client
from mediamop.modules.subber import subber_subsource_client as subsource_client
from mediamop.modules.subber import subber_yify_client as yify_client
from mediamop.modules.subber.subber_credentials_crypto import decrypt_subber_credentials_json, parse_provider_secrets_json
from mediamop.modules.subber.subber_opensubtitles_client import SubberRateLimitError
from mediamop.modules.subber.subber_provider_registry import (
    PROVIDER_ADDIC7ED,
    PROVIDER_GESTDOWN,
    PROVIDER_OPENSUBTITLES_COM,
    PROVIDER_OPENSUBTITLES_ORG,
    PROVIDER_PODNAPISI,
    PROVIDER_SUBDL,
    PROVIDER_SUBF2M,
    PROVIDER_SUBSCENE,
    PROVIDER_SUBSOURCE,
    PROVIDER_YIFY,
)
from mediamop.modules.refiner.refiner_operator_settings_service import ensure_refiner_operator_settings_row
from mediamop.modules.subber.subber_providers_model import SubberProviderRow
from mediamop.modules.subber.subber_providers_service import get_enabled_providers_ordered, provider_is_ready_for_search
from mediamop.modules.subber.subber_settings_model import SubberSettingsRow
from mediamop.modules.subber.subber_settings_service import language_preferences_list
from mediamop.modules.subber.subber_subtitle_state_model import SubberSubtitleState
from mediamop.modules.subber.subber_subtitle_state_service import mark_found, mark_missing
from mediamop.platform.file_lifecycle.guardrails import check_minimum_free_disk_space
from mediamop.platform.observability.failure_messages import operator_failure_from_exception

logger = logging.getLogger(__name__)


def _extract_srt_from_zip_or_raw(data: bytes) -> bytes:
    """If data is a ZIP extract first .srt; otherwise return as-is."""
    bio = io.BytesIO(data)
    if zipfile.is_zipfile(bio):
        bio.seek(0)
        with zipfile.ZipFile(bio) as zf:
            for name in zf.namelist():
                if name.lower().endswith(".srt"):
                    return zf.read(name)
    return data


def apply_path_mapping(file_path: str, arr_path: str, subber_path: str, enabled: bool) -> str:
    if not enabled:
        return file_path
    ap = (arr_path or "").strip()
    sp = (subber_path or "").strip()
    if not ap:
        return file_path
    fp = file_path
    if fp.startswith(ap):
        return sp + fp[len(ap) :]
    return file_path


def _opensubtitles_secrets_from_settings(settings: MediaMopSettings, row: SubberSettingsRow) -> tuple[str, str, str]:
    raw = decrypt_subber_credentials_json(settings, row.opensubtitles_credentials_ciphertext or "") or "{}"
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return "", "", ""
    sec = data.get("secrets") if isinstance(data.get("secrets"), dict) else {}
    return (
        str(sec.get("username") or "").strip(),
        str(sec.get("password") or "").strip(),
        str(sec.get("api_key") or "").strip(),
    )


def _opensubtitles_secrets_from_provider(settings: MediaMopSettings, prow: SubberProviderRow) -> tuple[str, str, str]:
    raw = decrypt_subber_credentials_json(settings, prow.credentials_ciphertext or "") or "{}"
    sec = parse_provider_secrets_json(prow.provider_key, raw)
    return (
        str(sec.get("username") or "").strip(),
        str(sec.get("password") or "").strip(),
        str(sec.get("api_key") or "").strip(),
    )


def opensubtitles_configured(settings: MediaMopSettings, row: SubberSettingsRow) -> bool:
    u, p, k = _opensubtitles_secrets_from_settings(settings, row)
    return bool(u and p and k)


def subber_any_search_configured(settings: MediaMopSettings, settings_row: SubberSettingsRow, db: Session) -> bool:
    if opensubtitles_configured(settings, settings_row):
        return True
    for prow in get_enabled_providers_ordered(db):
        if provider_is_ready_for_search(settings, prow):
            return True
    return False


def _search_query(state_row: SubberSubtitleState) -> str:
    if state_row.media_scope == "tv":
        st = (state_row.show_title or "").strip()
        sn = state_row.season_number
        en = state_row.episode_number
        if st and sn is not None and en is not None:
            return f"{st} S{int(sn):02d}E{int(en):02d}"
        return st or (state_row.episode_title or "").strip() or Path(state_row.file_path).stem
    title = (state_row.movie_title or "").strip()
    if state_row.movie_year is not None and title:
        return f"{title} {int(state_row.movie_year)}"
    return title or Path(state_row.file_path).stem


def _extract_file_id(item: dict) -> int | None:
    attrs = item.get("attributes")
    if not isinstance(attrs, dict):
        return None
    files = attrs.get("files")
    if isinstance(files, list) and files:
        first = files[0]
        if isinstance(first, dict) and first.get("file_id") is not None:
            try:
                return int(first["file_id"])
            except (TypeError, ValueError):
                return None
    fid = attrs.get("file_id")
    if fid is not None:
        try:
            return int(fid)
        except (TypeError, ValueError):
            return None
    return None


def _result_language(item: dict) -> str:
    attrs = item.get("attributes")
    if isinstance(attrs, dict):
        lang = str(attrs.get("language") or attrs.get("from_trusted") or "").strip().lower()
        if lang:
            return lang[:10]
    return ""


def _opensubtitles_hearing_impaired(item: dict) -> bool:
    attrs = item.get("attributes")
    if isinstance(attrs, dict):
        if attrs.get("hearing_impaired") in (True, 1, "1", "true"):
            return True
        hi = attrs.get("hearing_impaired")
        if isinstance(hi, str) and hi.lower() in ("true", "1", "yes"):
            return True
    return False


def _pick_best_opensubtitles_result(
    items: list[dict],
    prefs: list[str],
    *,
    exclude_hearing_impaired: bool,
) -> tuple[int | None, str | None]:
    pref_index = {p: i for i, p in enumerate(prefs)}
    scored: list[tuple[int, int, dict]] = []
    for it in items:
        if exclude_hearing_impaired and _opensubtitles_hearing_impaired(it):
            continue
        fid = _extract_file_id(it)
        if fid is None:
            continue
        lang = _result_language(it)
        rank = pref_index.get(lang, 999)
        scored.append((rank, fid, it))
    if not scored:
        return None, None
    scored.sort(key=lambda x: (x[0], x[1]))
    best = scored[0][2]
    return _extract_file_id(best), _result_language(best) or None


def _pick_best_podnapisi(
    items: list[dict],
    prefs: list[str],
    *,
    exclude_hearing_impaired: bool,
) -> tuple[str | None, str | None]:
    pref_index = {p: i for i, p in enumerate(prefs)}
    scored: list[tuple[int, str, dict]] = []
    for it in items:
        if exclude_hearing_impaired and bool(it.get("hearing_impaired")):
            continue
        sid = str(it.get("id") or "").strip()
        if not sid:
            continue
        lang = str(it.get("language") or "").strip().lower()[:10]
        rank = pref_index.get(lang, 999)
        scored.append((rank, sid, it))
    if not scored:
        return None, None
    scored.sort(key=lambda x: (x[0], x[1]))
    best = scored[0][2]
    return str(best.get("id") or "").strip() or None, str(best.get("language") or "").strip().lower()[:10] or None


def _mapped_media_path(settings_row: SubberSettingsRow, state_row: SubberSubtitleState) -> str:
    fp = state_row.file_path
    if state_row.media_scope == "tv":
        return apply_path_mapping(
            fp,
            (settings_row.sonarr_path_sonarr or "").strip(),
            (settings_row.sonarr_path_subber or "").strip(),
            bool(settings_row.sonarr_path_mapping_enabled),
        )
    return apply_path_mapping(
        fp,
        (settings_row.radarr_path_radarr or "").strip(),
        (settings_row.radarr_path_subber or "").strip(),
        bool(settings_row.radarr_path_mapping_enabled),
    )


def _write_srt_for_state(
    *,
    settings_row: SubberSettingsRow,
    state_row: SubberSubtitleState,
    lang: str,
    srt_bytes: bytes,
    provider_key: str,
    external_file_id: str,
    db: Session,
) -> None:
    mapped = _mapped_media_path(settings_row, state_row)
    stem = Path(mapped).stem
    folder = (settings_row.subtitle_folder or "").strip()
    out_dir = Path(folder) if folder else Path(mapped).parent
    out_dir.mkdir(parents=True, exist_ok=True)
    safe_lang = re.sub(r"[^a-z0-9_-]", "", lang)[:10] or "en"
    out_path = out_dir / f"{stem}.{safe_lang}.srt"
    guardrail = ensure_refiner_operator_settings_row(db)
    disk = check_minimum_free_disk_space(
        target_path=out_path,
        required_mb=guardrail.minimum_free_disk_space_mb,
    )
    if not disk.ok:
        raise RuntimeError(disk.message)
    out_path.write_bytes(srt_bytes)
    mark_found(
        db,
        int(state_row.id),
        subtitle_path=str(out_path.resolve()),
        opensubtitles_file_id=external_file_id,
        provider_key=provider_key,
    )


def _try_opensubtitles_provider(
    *,
    settings: MediaMopSettings,
    settings_row: SubberSettingsRow,
    state_row: SubberSubtitleState,
    db: Session,
    prow: SubberProviderRow,
    prefs: list[str],
    lang: str,
    exclude_hi: bool,
) -> bool:
    if prow.provider_key not in (PROVIDER_OPENSUBTITLES_ORG, PROVIDER_OPENSUBTITLES_COM):
        return False
    username, password, api_key = _opensubtitles_secrets_from_provider(settings, prow)
    if not api_key or not username or not password:
        return False
    token: str | None = None
    try:
        token = os_client.login(username, password, api_key)
        if lang not in prefs:
            prefs = [lang, *prefs]
        query = _search_query(state_row)
        season = state_row.season_number if state_row.media_scope == "tv" else None
        episode = state_row.episode_number if state_row.media_scope == "tv" else None
        items = os_client.search(
            token,
            api_key,
            query=query,
            season_number=season,
            episode_number=episode,
            languages=prefs,
            media_scope=state_row.media_scope,
        )
        file_id, picked_lang = _pick_best_opensubtitles_result(items, prefs, exclude_hearing_impaired=exclude_hi)
        if file_id is None:
            return False
        srt_bytes = os_client.download(token, api_key, file_id=file_id)
        _write_srt_for_state(
            settings_row=settings_row,
            state_row=state_row,
            lang=picked_lang or lang,
            srt_bytes=srt_bytes,
            provider_key=prow.provider_key,
            external_file_id=str(file_id),
            db=db,
        )
        return True
    except SubberRateLimitError:
        if token:
            try:
                os_client.logout(token, api_key)
            except Exception:
                pass
        raise
    finally:
        if token:
            try:
                os_client.logout(token, api_key)
            except Exception:
                pass


def _try_podnapisi(
    *,
    settings_row: SubberSettingsRow,
    state_row: SubberSubtitleState,
    db: Session,
    prow: SubberProviderRow,
    settings: MediaMopSettings,
    prefs: list[str],
    lang: str,
    exclude_hi: bool,
) -> bool:
    raw = decrypt_subber_credentials_json(settings, prow.credentials_ciphertext or "") or "{}"
    sec = parse_provider_secrets_json(prow.provider_key, raw)
    u = str(sec.get("username") or "").strip() or None
    p = str(sec.get("password") or "").strip() or None
    query = _search_query(state_row)
    season = state_row.season_number if state_row.media_scope == "tv" else None
    episode = state_row.episode_number if state_row.media_scope == "tv" else None
    items = podnapisi_client.search(
        query=query,
        season_number=season,
        episode_number=episode,
        languages=prefs if prefs else [lang],
        media_scope=state_row.media_scope,
        username=u,
        password=p,
    )
    sid, picked = _pick_best_podnapisi(items, prefs, exclude_hearing_impaired=exclude_hi)
    if not sid:
        return False
    try:
        data = podnapisi_client.download(subtitle_id=sid, username=u, password=p)
    except Exception:
        logger.exception("Podnapisi download failed state_id=%s", state_row.id)
        return False
    srt_bytes = podnapisi_client.extract_first_srt_from_zip(data)
    if not srt_bytes.strip():
        return False
    _write_srt_for_state(
        settings_row=settings_row,
        state_row=state_row,
        lang=picked or lang,
        srt_bytes=srt_bytes,
        provider_key=PROVIDER_PODNAPISI,
        external_file_id=sid,
        db=db,
    )
    return True


def _try_subscene(
    *,
    settings_row: SubberSettingsRow,
    state_row: SubberSubtitleState,
    db: Session,
    prefs: list[str],
    lang: str,
    exclude_hi: bool,
) -> bool:
    _ = (exclude_hi,)
    query = _search_query(state_row)
    season = state_row.season_number if state_row.media_scope == "tv" else None
    episode = state_row.episode_number if state_row.media_scope == "tv" else None
    items = subscene_client.search(
        query=query,
        season_number=season,
        episode_number=episode,
        languages=prefs if prefs else [lang],
        media_scope=state_row.media_scope,
    )
    if not items:
        return False
    return False


def _try_addic7ed(
    *,
    settings_row: SubberSettingsRow,
    state_row: SubberSubtitleState,
    db: Session,
    prow: SubberProviderRow,
    settings: MediaMopSettings,
    prefs: list[str],
    lang: str,
    exclude_hi: bool,
) -> bool:
    raw = decrypt_subber_credentials_json(settings, prow.credentials_ciphertext or "") or "{}"
    sec = parse_provider_secrets_json(prow.provider_key, raw)
    u = str(sec.get("username") or "").strip() or None
    p = str(sec.get("password") or "").strip() or None
    items = addic7ed_client.search(
        query=_search_query(state_row),
        season_number=state_row.season_number if state_row.media_scope == "tv" else None,
        episode_number=state_row.episode_number if state_row.media_scope == "tv" else None,
        languages=prefs if prefs else [lang],
        media_scope=state_row.media_scope,
        username=u,
        password=p,
    )
    if not items:
        return False
    _ = (settings_row, state_row, db, exclude_hi)
    return False


def _try_gestdown(
    *,
    settings_row: SubberSettingsRow,
    state_row: SubberSubtitleState,
    db: Session,
    prefs: list[str],
    lang: str,
    exclude_hi: bool,
) -> bool:
    if state_row.media_scope != "tv":
        return False
    items = gestdown_client.search(
        query=_search_query(state_row),
        season_number=state_row.season_number,
        episode_number=state_row.episode_number,
        languages=prefs if prefs else [lang],
    )
    for item in items:
        if exclude_hi and item.get("hearing_impaired"):
            continue
        dl_url = item.get("download_url", "")
        if not dl_url:
            continue
        try:
            raw = gestdown_client.download(download_url=dl_url)
            srt = _extract_srt_from_zip_or_raw(raw)
            if not srt.strip():
                continue
            picked_lang = str(item.get("language") or lang)
            _write_srt_for_state(
                settings_row=settings_row,
                state_row=state_row,
                lang=picked_lang,
                srt_bytes=srt,
                provider_key=PROVIDER_GESTDOWN,
                external_file_id=dl_url,
                db=db,
            )
            return True
        except Exception:
            logger.exception("Gestdown download failed state_id=%s", state_row.id)
            continue
    return False


def _try_subdl(
    *,
    settings_row: SubberSettingsRow,
    state_row: SubberSubtitleState,
    db: Session,
    prow: SubberProviderRow,
    settings: MediaMopSettings,
    prefs: list[str],
    lang: str,
    exclude_hi: bool,
) -> bool:
    from mediamop.modules.subber.subber_credentials_crypto import (
        decrypt_subber_credentials_json,
        parse_provider_secrets_json,
    )

    raw = decrypt_subber_credentials_json(settings, prow.credentials_ciphertext or "") or "{}"
    sec = parse_provider_secrets_json(prow.provider_key, raw)
    api_key = str(sec.get("api_key") or "").strip()
    if not api_key:
        return False
    items = subdl_client.search(
        api_key=api_key,
        query=_search_query(state_row),
        season_number=state_row.season_number if state_row.media_scope == "tv" else None,
        episode_number=state_row.episode_number if state_row.media_scope == "tv" else None,
        languages=prefs if prefs else [lang],
        media_scope=state_row.media_scope,
    )
    for item in items:
        if exclude_hi and item.get("hearing_impaired"):
            continue
        dl_url = item.get("download_url", "")
        if not dl_url:
            continue
        try:
            raw_data = subdl_client.download(download_url=dl_url)
            srt = _extract_srt_from_zip_or_raw(raw_data)
            if not srt.strip():
                continue
            picked_lang = item.get("language") or lang
            _write_srt_for_state(
                settings_row=settings_row,
                state_row=state_row,
                lang=picked_lang,
                srt_bytes=srt,
                provider_key=PROVIDER_SUBDL,
                external_file_id=dl_url,
                db=db,
            )
            return True
        except Exception:
            logger.exception("SubDL download failed state_id=%s", state_row.id)
            continue
    return False


def _try_subsource(
    *,
    settings_row: SubberSettingsRow,
    state_row: SubberSubtitleState,
    db: Session,
    prow: SubberProviderRow,
    settings: MediaMopSettings,
    prefs: list[str],
    lang: str,
    exclude_hi: bool,
) -> bool:
    from mediamop.modules.subber.subber_credentials_crypto import (
        decrypt_subber_credentials_json,
        parse_provider_secrets_json,
    )

    raw = decrypt_subber_credentials_json(settings, prow.credentials_ciphertext or "") or "{}"
    sec = parse_provider_secrets_json(prow.provider_key, raw)
    api_key = str(sec.get("api_key") or "").strip()
    if not api_key:
        return False
    items = subsource_client.search(
        api_key=api_key,
        query=_search_query(state_row),
        season_number=state_row.season_number if state_row.media_scope == "tv" else None,
        episode_number=state_row.episode_number if state_row.media_scope == "tv" else None,
        languages=prefs if prefs else [lang],
        media_scope=state_row.media_scope,
    )
    for item in items:
        if exclude_hi and item.get("hearing_impaired"):
            continue
        dl_url = item.get("download_url", "")
        if not dl_url:
            continue
        try:
            raw_data = subsource_client.download(download_url=dl_url, api_key=api_key)
            srt = _extract_srt_from_zip_or_raw(raw_data)
            if not srt.strip():
                continue
            picked_lang = item.get("language") or lang
            _write_srt_for_state(
                settings_row=settings_row,
                state_row=state_row,
                lang=picked_lang,
                srt_bytes=srt,
                provider_key=PROVIDER_SUBSOURCE,
                external_file_id=dl_url,
                db=db,
            )
            return True
        except Exception:
            logger.exception("SubSource download failed state_id=%s", state_row.id)
            continue
    return False


def _try_subf2m(
    *,
    settings_row: SubberSettingsRow,
    state_row: SubberSubtitleState,
    db: Session,
    prefs: list[str],
    lang: str,
    exclude_hi: bool,
) -> bool:
    items = subf2m_client.search(
        query=_search_query(state_row),
        season_number=state_row.season_number if state_row.media_scope == "tv" else None,
        episode_number=state_row.episode_number if state_row.media_scope == "tv" else None,
        languages=prefs if prefs else [lang],
        media_scope=state_row.media_scope,
    )
    for item in items:
        if exclude_hi and item.get("hearing_impaired"):
            continue
        dl_url = item.get("download_url", "")
        if not dl_url:
            continue
        try:
            raw_data = subf2m_client.download(download_url=dl_url)
            srt = _extract_srt_from_zip_or_raw(raw_data)
            if not srt.strip():
                continue
            picked_lang = item.get("language") or lang
            _write_srt_for_state(
                settings_row=settings_row,
                state_row=state_row,
                lang=picked_lang,
                srt_bytes=srt,
                provider_key=PROVIDER_SUBF2M,
                external_file_id=dl_url,
                db=db,
            )
            return True
        except Exception:
            logger.exception("Subf2m download failed state_id=%s", state_row.id)
            continue
    return False


def _try_yify(
    *,
    settings_row: SubberSettingsRow,
    state_row: SubberSubtitleState,
    db: Session,
    prefs: list[str],
    lang: str,
    exclude_hi: bool,
) -> bool:
    if state_row.media_scope != "movies":
        return False
    items = yify_client.search(
        query=_search_query(state_row),
        languages=prefs if prefs else [lang],
    )
    for item in items:
        if exclude_hi and item.get("hearing_impaired"):
            continue
        dl_url = item.get("download_url", "")
        if not dl_url:
            continue
        try:
            raw_data = yify_client.download(download_url=dl_url)
            srt = _extract_srt_from_zip_or_raw(raw_data)
            if not srt.strip():
                continue
            picked_lang = item.get("language") or lang
            _write_srt_for_state(
                settings_row=settings_row,
                state_row=state_row,
                lang=picked_lang,
                srt_bytes=srt,
                provider_key=PROVIDER_YIFY,
                external_file_id=dl_url,
                db=db,
            )
            return True
        except Exception:
            logger.exception("YifySubtitles download failed state_id=%s", state_row.id)
            continue
    return False


def _legacy_opensubtitles_search(
    *,
    settings: MediaMopSettings,
    settings_row: SubberSettingsRow,
    state_row: SubberSubtitleState,
    db: Session,
    exclude_hi: bool,
    retain_found_on_failure: bool = False,
) -> bool:
    username, password, api_key = _opensubtitles_secrets_from_settings(settings, settings_row)
    if not api_key or not username or not password:
        logger.warning("OpenSubtitles credentials incomplete; cannot search state_id=%s", state_row.id)
        if not retain_found_on_failure:
            mark_missing(db, int(state_row.id))
        return False
    token: str | None = None
    try:
        token = os_client.login(username, password, api_key)
        prefs = language_preferences_list(settings_row)
        lang = state_row.language_code.strip().lower()
        if lang not in prefs:
            prefs = [lang, *prefs]
        query = _search_query(state_row)
        season = state_row.season_number if state_row.media_scope == "tv" else None
        episode = state_row.episode_number if state_row.media_scope == "tv" else None
        items = os_client.search(
            token,
            api_key,
            query=query,
            season_number=season,
            episode_number=episode,
            languages=prefs,
            media_scope=state_row.media_scope,
        )
        file_id, picked_lang = _pick_best_opensubtitles_result(items, prefs, exclude_hearing_impaired=exclude_hi)
        if file_id is None:
            if not retain_found_on_failure:
                mark_missing(db, int(state_row.id))
            return False
        srt_bytes = os_client.download(token, api_key, file_id=file_id)
        _write_srt_for_state(
            settings_row=settings_row,
            state_row=state_row,
            lang=picked_lang or lang,
            srt_bytes=srt_bytes,
            provider_key=PROVIDER_OPENSUBTITLES_COM,
            external_file_id=str(file_id),
            db=db,
        )
        return True
    except SubberRateLimitError:
        if token:
            os_client.logout(token, api_key)
        raise
    except Exception:
        logger.exception("Subtitle search failed state_id=%s", state_row.id)
        if not retain_found_on_failure:
            mark_missing(db, int(state_row.id))
        return False
    finally:
        if token:
            try:
                os_client.logout(token, api_key)
            except Exception:
                pass


def search_and_download_subtitle(
    *,
    settings: MediaMopSettings,
    settings_row: SubberSettingsRow,
    state_row: SubberSubtitleState,
    db: Session,
    providers: list[SubberProviderRow] | None = None,
    retain_found_on_failure: bool = False,
    provider_events: list[dict[str, str]] | None = None,
) -> bool:
    """Search providers in order; legacy settings path when ``providers`` is empty.

    When ``retain_found_on_failure`` is True (subtitle upgrade path), failures do not call
    :func:`~mediamop.modules.subber.subber_subtitle_state_service.mark_missing`.
    """

    exclude_hi = bool(settings_row.exclude_hearing_impaired)
    prefs = language_preferences_list(settings_row)
    lang = state_row.language_code.strip().lower()

    use_rows = providers if providers is not None else get_enabled_providers_ordered(db)
    ready = [p for p in use_rows if provider_is_ready_for_search(settings, p)]

    if not ready:
        return _legacy_opensubtitles_search(
            settings=settings,
            settings_row=settings_row,
            state_row=state_row,
            db=db,
            exclude_hi=exclude_hi,
            retain_found_on_failure=retain_found_on_failure,
        )

    for prow in ready:
        try:
            pk = prow.provider_key
            if pk in (PROVIDER_OPENSUBTITLES_ORG, PROVIDER_OPENSUBTITLES_COM):
                if _try_opensubtitles_provider(
                    settings=settings,
                    settings_row=settings_row,
                    state_row=state_row,
                    db=db,
                    prow=prow,
                    prefs=prefs,
                    lang=lang,
                    exclude_hi=exclude_hi,
                ):
                    return True
            elif pk == PROVIDER_PODNAPISI:
                if _try_podnapisi(
                    settings_row=settings_row,
                    state_row=state_row,
                    db=db,
                    prow=prow,
                    settings=settings,
                    prefs=prefs,
                    lang=lang,
                    exclude_hi=exclude_hi,
                ):
                    return True
            elif pk == PROVIDER_SUBSCENE:
                if _try_subscene(
                    settings_row=settings_row,
                    state_row=state_row,
                    db=db,
                    prefs=prefs,
                    lang=lang,
                    exclude_hi=exclude_hi,
                ):
                    return True
            elif pk == PROVIDER_ADDIC7ED:
                if _try_addic7ed(
                    settings_row=settings_row,
                    state_row=state_row,
                    db=db,
                    prow=prow,
                    settings=settings,
                    prefs=prefs,
                    lang=lang,
                    exclude_hi=exclude_hi,
                ):
                    return True
            elif pk == PROVIDER_GESTDOWN:
                if _try_gestdown(
                    settings_row=settings_row,
                    state_row=state_row,
                    db=db,
                    prefs=prefs,
                    lang=lang,
                    exclude_hi=exclude_hi,
                ):
                    return True
            elif pk == PROVIDER_SUBDL:
                if _try_subdl(
                    settings_row=settings_row,
                    state_row=state_row,
                    db=db,
                    prow=prow,
                    settings=settings,
                    prefs=prefs,
                    lang=lang,
                    exclude_hi=exclude_hi,
                ):
                    return True
            elif pk == PROVIDER_SUBSOURCE:
                if _try_subsource(
                    settings_row=settings_row,
                    state_row=state_row,
                    db=db,
                    prow=prow,
                    settings=settings,
                    prefs=prefs,
                    lang=lang,
                    exclude_hi=exclude_hi,
                ):
                    return True
            elif pk == PROVIDER_SUBF2M:
                if _try_subf2m(
                    settings_row=settings_row,
                    state_row=state_row,
                    db=db,
                    prefs=prefs,
                    lang=lang,
                    exclude_hi=exclude_hi,
                ):
                    return True
            elif pk == PROVIDER_YIFY:
                if _try_yify(
                    settings_row=settings_row,
                    state_row=state_row,
                    db=db,
                    prefs=prefs,
                    lang=lang,
                    exclude_hi=exclude_hi,
                ):
                    return True
        except SubberRateLimitError as exc:
            failure = operator_failure_from_exception(
                module="Subber",
                action="subtitle search",
                exc=exc,
                provider=str(prow.provider_key),
                recoverable=True,
                continuation="Subber skipped this provider and continued with the next enabled provider.",
            )
            message = failure.message
            logger.warning("%s state_id=%s", message, state_row.id)
            if provider_events is not None:
                provider_events.append(
                    {
                        "provider": str(prow.provider_key),
                        "result": "skipped",
                        "reason": "rate_limited",
                        "message": message,
                        **failure.as_dict(),
                    }
                )
            continue
        except Exception as exc:  # noqa: BLE001 - continue to next provider
            failure = operator_failure_from_exception(
                module="Subber",
                action="subtitle search",
                exc=exc,
                provider=str(prow.provider_key),
                recoverable=True,
                continuation="Subber skipped this provider and continued with the next enabled provider.",
            )
            logger.exception("%s state_id=%s", failure.message, state_row.id)
            if provider_events is not None:
                provider_events.append(
                    {
                        "provider": str(prow.provider_key),
                        "result": "skipped",
                        "reason": failure.kind,
                        "message": failure.message,
                        **failure.as_dict(),
                    }
                )
            continue

    if not retain_found_on_failure:
        mark_missing(db, int(state_row.id))
    return False
