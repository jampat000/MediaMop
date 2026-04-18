"""Per media file + language subtitle tracking for Subber."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from mediamop.core.db import Base


class SubberSubtitleState(Base):
    __tablename__ = "subber_subtitle_state"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    media_scope: Mapped[str] = mapped_column(String(10), nullable=False)
    file_path: Mapped[str] = mapped_column(String(2000), nullable=False)
    language_code: Mapped[str] = mapped_column(String(10), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="missing")
    subtitle_path: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    opensubtitles_file_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    last_searched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    search_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    source: Mapped[str | None] = mapped_column(String(20), nullable=True)
    show_title: Mapped[str | None] = mapped_column(String(500), nullable=True)
    season_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    episode_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    episode_title: Mapped[str | None] = mapped_column(String(500), nullable=True)
    movie_title: Mapped[str | None] = mapped_column(String(500), nullable=True)
    movie_year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    sonarr_episode_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    radarr_movie_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
