"""Singleton row for Sonarr/Radarr library connection and legacy lane columns (SQLite ``arr_library_operator_settings``)."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, Integer, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from mediamop.core.db import Base


class ArrLibraryOperatorSettingsRow(Base):
    """One row (``id = 1``) — Sonarr/Radarr URLs and keys used by Refiner/Pruner/Subber."""

    __tablename__ = "arr_library_operator_settings"
    __table_args__ = (CheckConstraint("id = 1", name="ck_arr_library_operator_settings_singleton"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    sonarr_missing_search_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="0")
    sonarr_missing_search_max_items_per_run: Mapped[int] = mapped_column(Integer, nullable=False, server_default="50")
    sonarr_missing_search_retry_delay_minutes: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="1440"
    )
    sonarr_missing_search_schedule_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="0")
    sonarr_missing_search_schedule_days: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    sonarr_missing_search_schedule_start: Mapped[str] = mapped_column(Text, nullable=False, server_default="00:00")
    sonarr_missing_search_schedule_end: Mapped[str] = mapped_column(Text, nullable=False, server_default="23:59")
    sonarr_missing_search_schedule_interval_seconds: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="3600"
    )

    sonarr_upgrade_search_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="0")
    sonarr_upgrade_search_max_items_per_run: Mapped[int] = mapped_column(Integer, nullable=False, server_default="50")
    sonarr_upgrade_search_retry_delay_minutes: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="1440"
    )
    sonarr_upgrade_search_schedule_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="0")
    sonarr_upgrade_search_schedule_days: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    sonarr_upgrade_search_schedule_start: Mapped[str] = mapped_column(Text, nullable=False, server_default="00:00")
    sonarr_upgrade_search_schedule_end: Mapped[str] = mapped_column(Text, nullable=False, server_default="23:59")
    sonarr_upgrade_search_schedule_interval_seconds: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="3600"
    )

    radarr_missing_search_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="0")
    radarr_missing_search_max_items_per_run: Mapped[int] = mapped_column(Integer, nullable=False, server_default="50")
    radarr_missing_search_retry_delay_minutes: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="1440"
    )
    radarr_missing_search_schedule_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="0")
    radarr_missing_search_schedule_days: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    radarr_missing_search_schedule_start: Mapped[str] = mapped_column(Text, nullable=False, server_default="00:00")
    radarr_missing_search_schedule_end: Mapped[str] = mapped_column(Text, nullable=False, server_default="23:59")
    radarr_missing_search_schedule_interval_seconds: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="3600"
    )

    radarr_upgrade_search_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="0")
    radarr_upgrade_search_max_items_per_run: Mapped[int] = mapped_column(Integer, nullable=False, server_default="50")
    radarr_upgrade_search_retry_delay_minutes: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="1440"
    )
    radarr_upgrade_search_schedule_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="0")
    radarr_upgrade_search_schedule_days: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    radarr_upgrade_search_schedule_start: Mapped[str] = mapped_column(Text, nullable=False, server_default="00:00")
    radarr_upgrade_search_schedule_end: Mapped[str] = mapped_column(Text, nullable=False, server_default="23:59")
    radarr_upgrade_search_schedule_interval_seconds: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="3600"
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    sonarr_connection_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="1")
    sonarr_connection_base_url: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    sonarr_connection_api_key_ciphertext: Mapped[str | None] = mapped_column(Text, nullable=True)
    sonarr_last_connection_test_ok: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    sonarr_last_connection_test_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    sonarr_last_connection_test_detail: Mapped[str | None] = mapped_column(Text, nullable=True)

    radarr_connection_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="1")
    radarr_connection_base_url: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    radarr_connection_api_key_ciphertext: Mapped[str | None] = mapped_column(Text, nullable=True)
    radarr_last_connection_test_ok: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    radarr_last_connection_test_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    radarr_last_connection_test_detail: Mapped[str | None] = mapped_column(Text, nullable=True)
