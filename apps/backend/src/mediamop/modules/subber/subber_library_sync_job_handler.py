"""Handlers for ``subber.library_sync.{tv,movies}.v1`` — pull full *arr libraries into subtitle state."""

from __future__ import annotations

import json
import os
from collections.abc import Callable

from sqlalchemy.orm import Session, sessionmaker

from mediamop.core.config import MediaMopSettings
from mediamop.modules.subber import subber_activity
from mediamop.modules.subber.subber_arr_client import (
    SubberArrClientError,
    get_radarr_movies,
    get_sonarr_episode_files,
    get_sonarr_episodes,
    get_sonarr_series,
)
from mediamop.modules.subber.subber_credentials_crypto import decrypt_subber_credentials_json
from mediamop.modules.subber.subber_job_kinds import SUBBER_JOB_KIND_LIBRARY_SYNC_MOVIES, SUBBER_JOB_KIND_LIBRARY_SYNC_TV
from mediamop.modules.subber.subber_settings_model import SubberSettingsRow
from mediamop.modules.subber.subber_settings_service import ensure_subber_settings_row, language_preferences_list
from mediamop.modules.subber.subber_subtitle_search_service import apply_path_mapping
from mediamop.modules.subber.subber_subtitle_state_service import upsert_subtitle_state
from mediamop.modules.subber.worker_loop import SubberJobWorkContext
from mediamop.platform.activity import constants as C


def _arr_api_key(settings: MediaMopSettings, row: SubberSettingsRow, *, radarr: bool) -> str:
    ct = row.radarr_credentials_ciphertext if radarr else row.sonarr_credentials_ciphertext
    raw = decrypt_subber_credentials_json(settings, ct or "") or "{}"
    try:
        kd = json.loads(raw)
    except json.JSONDecodeError:
        kd = {}
    sec = kd.get("secrets") if isinstance(kd.get("secrets"), dict) else {}
    return str(sec.get("api_key") or "").strip()


def _mapped_media_path(settings_row: SubberSettingsRow, *, media_scope: str, arr_file_path: str) -> str:
    fp = arr_file_path.strip()
    if media_scope == "tv":
        return apply_path_mapping(
            fp,
            str(settings_row.sonarr_path_sonarr or ""),
            str(settings_row.sonarr_path_subber or ""),
            bool(settings_row.sonarr_path_mapping_enabled),
        )
    return apply_path_mapping(
        fp,
        str(settings_row.radarr_path_radarr or ""),
        str(settings_row.radarr_path_subber or ""),
        bool(settings_row.radarr_path_mapping_enabled),
    )


def _detect_subtitle_path(settings_row: SubberSettingsRow, mapped_media_path: str, lang: str) -> tuple[str | None, str]:
    """Return (subtitle_path_or_none, status found|missing) for sidecar + optional subtitle_folder."""
    lc = lang.strip().lower()
    base, _ext = os.path.splitext(mapped_media_path.strip())
    candidates: list[str] = [f"{base}.{lc}.srt"]
    sub_folder = (settings_row.subtitle_folder or "").strip()
    if sub_folder:
        base_name = os.path.basename(base)
        candidates.append(os.path.join(sub_folder, f"{base_name}.{lc}.srt"))
    for c in candidates:
        try:
            if c and os.path.isfile(c):
                return c, "found"
        except OSError:
            continue
    return None, "missing"


def _episode_file_path(ep: dict, episode_file_id_to_path: dict[int, str]) -> str:
    ef = ep.get("episodeFile")
    if isinstance(ef, dict):
        p = str(ef.get("path") or ef.get("relativePath") or "").strip()
        if p:
            return p
        efid = ef.get("id")
        if efid is not None and str(efid).strip().isdigit():
            return episode_file_id_to_path.get(int(efid), "")
    return ""


def make_subber_library_sync_movies_handler(
    settings: MediaMopSettings,
    session_factory: sessionmaker[Session],
) -> Callable[[SubberJobWorkContext], None]:
    def handle(ctx: SubberJobWorkContext) -> None:
        _ = json.loads(ctx.payload_json or "{}")
        with session_factory() as session:
            with session.begin():
                row = ensure_subber_settings_row(session)
                api_key = _arr_api_key(settings, row, radarr=True)
                base = (row.radarr_base_url or "").strip()
                if not base or not api_key:
                    subber_activity.record_subber_activity(
                        session,
                        event_type=C.SUBBER_LIBRARY_SYNC_COMPLETED,
                        title="Radarr library sync skipped — not configured",
                        detail={"reason": "not_configured"},
                    )
                    return
                try:
                    movies = get_radarr_movies(base, api_key)
                except SubberArrClientError as e:
                    subber_activity.record_subber_activity(
                        session,
                        event_type=C.SUBBER_LIBRARY_SYNC_COMPLETED,
                        title="Radarr library sync failed",
                        detail={"error": str(e)[:500]},
                    )
                    raise
                langs = language_preferences_list(row)
                processed = 0
                found_subs = 0
                for m in movies:
                    if not m.get("hasFile"):
                        continue
                    mf = m.get("movieFile")
                    if not isinstance(mf, dict):
                        continue
                    fp = str(mf.get("path") or "").strip()
                    if not fp:
                        continue
                    processed += 1
                    mid = m.get("id")
                    mid_i = int(mid) if mid is not None and str(mid).strip().isdigit() else None
                    title = str(m.get("title") or "").strip()
                    yr = m.get("year")
                    year_i = int(yr) if yr is not None and str(yr).strip().lstrip("-").isdigit() else None
                    mapped = _mapped_media_path(row, media_scope="movies", arr_file_path=fp)
                    for lang in langs:
                        sub_path, st = _detect_subtitle_path(row, mapped, lang)
                        if st == "found":
                            found_subs += 1
                        upsert_subtitle_state(
                            session,
                            media_scope="movies",
                            file_path=fp,
                            language_code=lang,
                            status=st,
                            subtitle_path=sub_path,
                            source="sync",
                            movie_title=title or None,
                            movie_year=year_i,
                            radarr_movie_id=mid_i,
                        )
                subber_activity.record_subber_activity(
                    session,
                    event_type=C.SUBBER_LIBRARY_SYNC_COMPLETED,
                    title=f"Radarr library sync complete — {processed} movies processed, {found_subs} subtitles already found",
                    detail={"movies": processed, "subtitles_found": found_subs},
                )

    return handle


def make_subber_library_sync_tv_handler(
    settings: MediaMopSettings,
    session_factory: sessionmaker[Session],
) -> Callable[[SubberJobWorkContext], None]:
    def handle(ctx: SubberJobWorkContext) -> None:
        _ = json.loads(ctx.payload_json or "{}")
        with session_factory() as session:
            with session.begin():
                row = ensure_subber_settings_row(session)
                api_key = _arr_api_key(settings, row, radarr=False)
                base = (row.sonarr_base_url or "").strip()
                if not base or not api_key:
                    subber_activity.record_subber_activity(
                        session,
                        event_type=C.SUBBER_LIBRARY_SYNC_COMPLETED,
                        title="Sonarr library sync skipped — not configured",
                        detail={"reason": "not_configured"},
                    )
                    return
                try:
                    series_list = get_sonarr_series(base, api_key)
                except SubberArrClientError as e:
                    subber_activity.record_subber_activity(
                        session,
                        event_type=C.SUBBER_LIBRARY_SYNC_COMPLETED,
                        title="Sonarr library sync failed",
                        detail={"error": str(e)[:500]},
                    )
                    raise
                langs = language_preferences_list(row)
                series_count = 0
                episodes_processed = 0
                found_subs = 0
                for ser in series_list:
                    sid = ser.get("id")
                    if sid is None or not str(sid).strip().isdigit():
                        continue
                    series_id = int(sid)
                    series_count += 1
                    show_title = str(ser.get("title") or "").strip() or None
                    try:
                        ep_files = get_sonarr_episode_files(base, api_key, series_id)
                    except SubberArrClientError:
                        ep_files = []
                    episode_file_id_to_path: dict[int, str] = {}
                    for ef in ep_files:
                        if not isinstance(ef, dict):
                            continue
                        fid = ef.get("id")
                        path = str(ef.get("path") or "").strip()
                        if fid is not None and str(fid).strip().isdigit() and path:
                            episode_file_id_to_path[int(fid)] = path
                    try:
                        episodes = get_sonarr_episodes(base, api_key, series_id)
                    except SubberArrClientError:
                        continue
                    for ep in episodes:
                        if not ep.get("hasFile"):
                            continue
                        fp = _episode_file_path(ep, episode_file_id_to_path)
                        if not fp:
                            continue
                        episodes_processed += 1
                        epi_id = ep.get("id")
                        epi_i = int(epi_id) if epi_id is not None and str(epi_id).strip().isdigit() else None
                        sn = ep.get("seasonNumber")
                        en = ep.get("episodeNumber")
                        son = int(sn) if sn is not None and str(sn).strip().lstrip("-").isdigit() else None
                        epn = int(en) if en is not None and str(en).strip().lstrip("-").isdigit() else None
                        et = ep.get("title")
                        ep_title = str(et).strip() if et is not None else None
                        mapped = _mapped_media_path(row, media_scope="tv", arr_file_path=fp)
                        for lang in langs:
                            sub_path, st = _detect_subtitle_path(row, mapped, lang)
                            if st == "found":
                                found_subs += 1
                            upsert_subtitle_state(
                                session,
                                media_scope="tv",
                                file_path=fp,
                                language_code=lang,
                                status=st,
                                subtitle_path=sub_path,
                                source="sync",
                                show_title=show_title,
                                season_number=son,
                                episode_number=epn,
                                episode_title=ep_title,
                                sonarr_episode_id=epi_i,
                            )
                subber_activity.record_subber_activity(
                    session,
                    event_type=C.SUBBER_LIBRARY_SYNC_COMPLETED,
                    title=(
                        f"Sonarr library sync complete — {series_count} series processed, "
                        f"{episodes_processed} episodes with files, {found_subs} subtitles already found"
                    ),
                    detail={"series": series_count, "episodes": episodes_processed, "subtitles_found": found_subs},
                )

    return handle


def register_library_sync_handlers(
    settings: MediaMopSettings,
    session_factory: sessionmaker[Session],
) -> dict[str, Callable[[SubberJobWorkContext], None]]:
    return {
        SUBBER_JOB_KIND_LIBRARY_SYNC_MOVIES: make_subber_library_sync_movies_handler(settings, session_factory),
        SUBBER_JOB_KIND_LIBRARY_SYNC_TV: make_subber_library_sync_tv_handler(settings, session_factory),
    }
