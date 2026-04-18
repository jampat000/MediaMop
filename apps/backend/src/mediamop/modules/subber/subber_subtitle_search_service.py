"""Search and download subtitles via OpenSubtitles."""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path

from sqlalchemy.orm import Session

from mediamop.core.config import MediaMopSettings
from mediamop.modules.subber import subber_opensubtitles_client as os_client
from mediamop.modules.subber.subber_credentials_crypto import decrypt_subber_credentials_json
from mediamop.modules.subber.subber_opensubtitles_client import SubberRateLimitError
from mediamop.modules.subber.subber_settings_model import SubberSettingsRow
from mediamop.modules.subber.subber_settings_service import language_preferences_list
from mediamop.modules.subber.subber_subtitle_state_model import SubberSubtitleState
from mediamop.modules.subber.subber_subtitle_state_service import mark_found, mark_missing

logger = logging.getLogger(__name__)


def _opensubtitles_secrets(settings: MediaMopSettings, row: SubberSettingsRow) -> tuple[str, str, str]:
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


def opensubtitles_configured(settings: MediaMopSettings, row: SubberSettingsRow) -> bool:
    u, p, k = _opensubtitles_secrets(settings, row)
    return bool(u and p and k)


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


def _pick_best_result(
    items: list[dict],
    prefs: list[str],
) -> tuple[int | None, str | None]:
    """Return (file_id, detected_lang) for best match following ``prefs`` order."""

    pref_index = {p: i for i, p in enumerate(prefs)}
    scored: list[tuple[int, int, dict]] = []
    for it in items:
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


def search_and_download_subtitle(
    *,
    settings: MediaMopSettings,
    settings_row: SubberSettingsRow,
    state_row: SubberSubtitleState,
    db: Session,
) -> bool:
    """Login, search, download SRT, write next to media (or subtitle folder). Return True if saved."""

    username, password, api_key = _opensubtitles_secrets(settings, settings_row)
    if not api_key or not username or not password:
        logger.warning("OpenSubtitles credentials incomplete; cannot search state_id=%s", state_row.id)
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
        file_id, _picked_lang = _pick_best_result(items, prefs)
        if file_id is None:
            mark_missing(db, int(state_row.id))
            return False
        srt_bytes = os_client.download(token, api_key, file_id=file_id)
        stem = Path(state_row.file_path).stem
        folder = (settings_row.subtitle_folder or "").strip()
        out_dir = Path(folder) if folder else Path(state_row.file_path).parent
        out_dir.mkdir(parents=True, exist_ok=True)
        safe_lang = re.sub(r"[^a-z0-9_-]", "", lang)[:10] or "en"
        out_path = out_dir / f"{stem}.{safe_lang}.srt"
        out_path.write_bytes(srt_bytes)
        mark_found(
            db,
            int(state_row.id),
            subtitle_path=str(out_path.resolve()),
            opensubtitles_file_id=str(file_id),
        )
        return True
    except SubberRateLimitError:
        if token:
            os_client.logout(token, api_key)
        raise
    except Exception:
        logger.exception("Subtitle search failed state_id=%s", state_row.id)
        mark_missing(db, int(state_row.id))
        return False
    finally:
        if token:
            try:
                os_client.logout(token, api_key)
            except Exception:
                pass
