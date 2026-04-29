"""Pruner media server instance — one row per connected server (Emby / Jellyfin / Plex)."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, Integer, String, Text, UniqueConstraint, func, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from mediamop.core.db import Base

if TYPE_CHECKING:
    from mediamop.modules.pruner.pruner_scope_settings_model import PrunerScopeSettings


class PrunerServerInstance(Base):
    """Operator-registered server; credentials stored as encrypted JSON (see ``pruner_credentials``)."""

    __tablename__ = "pruner_server_instances"
    __table_args__ = (UniqueConstraint("provider", "normalized_base_url", name="uq_pruner_server_provider_normalized_url"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    provider: Mapped[str] = mapped_column(String(16), nullable=False)
    display_name: Mapped[str] = mapped_column(String(200), nullable=False)
    base_url: Mapped[str] = mapped_column(String(512), nullable=False)
    normalized_base_url: Mapped[str] = mapped_column(String(512), nullable=False)
    credentials_ciphertext: Mapped[str] = mapped_column(Text, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("1"))
    last_connection_test_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_connection_test_ok: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    last_connection_test_detail: Mapped[str | None] = mapped_column(Text, nullable=True)
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

    scope_settings: Mapped[list["PrunerScopeSettings"]] = relationship(
        "PrunerScopeSettings",
        back_populates="server_instance",
        cascade="all, delete-orphan",
    )
