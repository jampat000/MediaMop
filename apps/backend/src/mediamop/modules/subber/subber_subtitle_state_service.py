"""CRUD for ``subber_subtitle_state``."""

from __future__ import annotations

import os
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from mediamop.modules.subber.subber_subtitle_state_model import SubberSubtitleState


def upsert_subtitle_state(
    session: Session,
    *,
    media_scope: str,
    file_path: str,
    language_code: str,
    status: str = "missing",
    subtitle_path: str | None = None,
    opensubtitles_file_id: str | None = None,
    last_searched_at: datetime | None = None,
    source: str | None = None,
    show_title: str | None = None,
    season_number: int | None = None,
    episode_number: int | None = None,
    episode_title: str | None = None,
    movie_title: str | None = None,
    movie_year: int | None = None,
    sonarr_episode_id: int | None = None,
    radarr_movie_id: int | None = None,
) -> SubberSubtitleState:
    lang = language_code.strip().lower()
    fp = file_path.strip()
    row = session.scalars(
        select(SubberSubtitleState).where(
            SubberSubtitleState.file_path == fp,
            SubberSubtitleState.language_code == lang,
        ),
    ).one_or_none()
    now = datetime.now(timezone.utc)
    if row is None:
        row = SubberSubtitleState(
            media_scope=media_scope,
            file_path=fp,
            language_code=lang,
            status=status,
            subtitle_path=subtitle_path,
            opensubtitles_file_id=opensubtitles_file_id,
            last_searched_at=last_searched_at,
            source=source,
            show_title=show_title,
            season_number=season_number,
            episode_number=episode_number,
            episode_title=episode_title,
            movie_title=movie_title,
            movie_year=movie_year,
            sonarr_episode_id=sonarr_episode_id,
            radarr_movie_id=radarr_movie_id,
        )
        session.add(row)
    else:
        row.media_scope = media_scope
        prev = (row.status or "").strip().lower()
        new_st = (status or "").strip().lower() if status else ""
        if new_st:
            if prev == "found" and new_st == "missing":
                pass
            else:
                row.status = status
        if subtitle_path is not None:
            row.subtitle_path = subtitle_path
        if opensubtitles_file_id is not None:
            row.opensubtitles_file_id = opensubtitles_file_id
        if last_searched_at is not None:
            row.last_searched_at = last_searched_at
        if source is not None:
            row.source = source
        if show_title is not None:
            row.show_title = show_title
        if season_number is not None:
            row.season_number = season_number
        if episode_number is not None:
            row.episode_number = episode_number
        if episode_title is not None:
            row.episode_title = episode_title
        if movie_title is not None:
            row.movie_title = movie_title
        if movie_year is not None:
            row.movie_year = movie_year
        if sonarr_episode_id is not None:
            row.sonarr_episode_id = sonarr_episode_id
        if radarr_movie_id is not None:
            row.radarr_movie_id = radarr_movie_id
        row.updated_at = now
    session.flush()
    return row


def get_missing_for_scope(session: Session, media_scope: str) -> list[SubberSubtitleState]:
    return list(
        session.scalars(
            select(SubberSubtitleState)
            .where(
                SubberSubtitleState.media_scope == media_scope,
                SubberSubtitleState.status == "missing",
            )
            .order_by(SubberSubtitleState.id.asc()),
        ).all(),
    )


def get_all_for_scope(session: Session, media_scope: str) -> list[SubberSubtitleState]:
    return list(
        session.scalars(
            select(SubberSubtitleState)
            .where(SubberSubtitleState.media_scope == media_scope)
            .order_by(SubberSubtitleState.id.asc()),
        ).all(),
    )


def get_state_by_id(session: Session, state_id: int) -> SubberSubtitleState | None:
    return session.scalars(select(SubberSubtitleState).where(SubberSubtitleState.id == state_id)).one_or_none()


def mark_found(
    session: Session,
    state_id: int,
    *,
    subtitle_path: str,
    opensubtitles_file_id: str,
    provider_key: str | None = None,
) -> None:
    row = session.scalars(select(SubberSubtitleState).where(SubberSubtitleState.id == state_id)).one_or_none()
    if row is None:
        return
    row.status = "found"
    row.subtitle_path = subtitle_path
    row.opensubtitles_file_id = opensubtitles_file_id
    if provider_key is not None:
        row.provider_key = provider_key.strip()[:50] or None
    row.updated_at = datetime.now(timezone.utc)
    session.flush()


def mark_for_upgrade(session: Session, state_id: int, *, increment_count: bool = True) -> None:
    row = session.scalars(select(SubberSubtitleState).where(SubberSubtitleState.id == state_id)).one_or_none()
    if row is None:
        return
    row.upgraded_at = datetime.now(timezone.utc)
    if increment_count:
        row.upgrade_count = int(row.upgrade_count or 0) + 1
    row.updated_at = datetime.now(timezone.utc)
    session.flush()


def get_candidates_for_upgrade(session: Session, since_days: int) -> list[SubberSubtitleState]:
    from datetime import timedelta

    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=max(1, int(since_days)))
    rows = list(
        session.scalars(
            select(SubberSubtitleState)
            .where(SubberSubtitleState.status == "found")
            .order_by(SubberSubtitleState.id.asc()),
        ).all(),
    )
    out: list[SubberSubtitleState] = []
    for r in rows:
        sp = (r.subtitle_path or "").strip()
        if not sp:
            continue
        try:
            if not os.path.isfile(sp):
                continue
        except OSError:
            continue
        lu = r.upgraded_at
        if lu is None:
            out.append(r)
            continue
        luu = lu if lu.tzinfo else lu.replace(tzinfo=timezone.utc)
        if luu < cutoff:
            out.append(r)
    return out


def mark_searching(session: Session, state_id: int) -> None:
    row = session.scalars(select(SubberSubtitleState).where(SubberSubtitleState.id == state_id)).one_or_none()
    if row is None:
        return
    row.status = "searching"
    row.search_count = int(row.search_count or 0) + 1
    row.last_searched_at = datetime.now(timezone.utc)
    row.updated_at = datetime.now(timezone.utc)
    session.flush()


def mark_skipped(session: Session, state_id: int) -> None:
    row = session.scalars(select(SubberSubtitleState).where(SubberSubtitleState.id == state_id)).one_or_none()
    if row is None:
        return
    row.status = "skipped"
    row.updated_at = datetime.now(timezone.utc)
    session.flush()


def mark_missing(session: Session, state_id: int) -> None:
    row = session.scalars(select(SubberSubtitleState).where(SubberSubtitleState.id == state_id)).one_or_none()
    if row is None:
        return
    row.status = "missing"
    row.updated_at = datetime.now(timezone.utc)
    session.flush()
