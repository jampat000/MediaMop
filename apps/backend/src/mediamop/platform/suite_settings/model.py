"""Singleton row for suite-level Settings fields shown across the signed-in app."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, Integer, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from mediamop.core.db import Base


class SuiteSettingsRow(Base):
    """One row (``id = 1``) — suite-owned global settings only."""

    __tablename__ = "suite_settings"
    __table_args__ = (CheckConstraint("id = 1", name="ck_suite_settings_singleton"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    product_display_name: Mapped[str] = mapped_column(Text, nullable=False, server_default="MediaMop")
    signed_in_home_notice: Mapped[str | None] = mapped_column(Text, nullable=True)
    setup_wizard_state: Mapped[str] = mapped_column(Text, nullable=False, server_default="pending")
    app_timezone: Mapped[str] = mapped_column(Text, nullable=False, server_default="UTC")
    log_retention_days: Mapped[int] = mapped_column(Integer, nullable=False, server_default="30")
    configuration_backup_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="0")
    configuration_backup_interval_hours: Mapped[int] = mapped_column(Integer, nullable=False, server_default="24")
    configuration_backup_preferred_time: Mapped[str] = mapped_column(Text, nullable=False, server_default="02:00")
    configuration_backup_last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Pause lives on the suite, not on Refiner, so Pruner can honour the same switch
    # without a second one appearing next to it.
    processing_paused: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="0")
    # A pause with an expiry is one an operator cannot forget to lift. Null means
    # "until I say otherwise", which is a deliberate choice rather than the only option.
    processing_paused_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Usually you want to keep noticing files while declining to work on them, so this
    # defaults on: pausing stops processing, not detection.
    scan_while_paused: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="1")

    # The metadata provider. On the suite rather than on Refiner because "what is this
    # film's original language" is not a Refiner question — Pruner will want the same
    # answer. The base URL is configurable so a cache or gateway in front of TMDb works
    # (#343). The key is encrypted with the same helper the manager credentials use.
    metadata_provider: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    metadata_provider_base_url: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    metadata_provider_key_ciphertext: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
