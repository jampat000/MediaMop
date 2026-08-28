"""A Refiner library is a row (SQLite). See ADR-0014.

Refiner was configured by two hardcoded scopes, and they were not data — they were the
schema. ``refiner_path_settings`` held movie paths and then the same three again as
``refiner_tv_*``; ``refiner_remux_rules_settings`` held ten fields and then the same ten
``tv_``-prefixed. A third library — 4K, kids, a re-encode staging folder — needed a
migration.

``media_scope`` survives as a *property* of a library, because it still selects which
cleanup behaviour applies (a movie release folder versus a whole season folder). It stops
being the key the module partitions on.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from mediamop.core.db import Base

REFINER_MEDIA_SCOPES: tuple[str, ...] = ("movie", "tv")


class RefinerRuleSetRow(Base):
    """Audio and subtitle handling, named so two libraries can share one.

    Not inline on the library: two libraries wanting identical handling should share one
    rule set, and changing it once should change both. Inline is simpler for exactly one
    library, which is the situation ADR-0014 exists to end.
    """

    __tablename__ = "refiner_rule_sets"
    __table_args__ = (UniqueConstraint("name", name="uq_refiner_rule_sets_name"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)

    primary_audio_lang: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    secondary_audio_lang: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    tertiary_audio_lang: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    default_audio_slot: Mapped[str] = mapped_column(Text, nullable=False, server_default="primary")
    remove_commentary: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="0")
    subtitle_mode: Mapped[str] = mapped_column(Text, nullable=False, server_default="keep_all")
    subtitle_langs_csv: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    preserve_forced_subs: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="1")
    preserve_default_subs: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="1")
    audio_preference_mode: Mapped[str] = mapped_column(Text, nullable=False, server_default="preferred_langs_quality")

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    libraries: Mapped[list[RefinerLibraryRow]] = relationship(back_populates="rule_set")


class RefinerLibraryRow(Base):
    """One configured Refiner library."""

    __tablename__ = "refiner_libraries"
    __table_args__ = (UniqueConstraint("name", name="uq_refiner_libraries_name"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="1")
    # Selects the cleanup behaviour (movie release folder vs whole season folder). No
    # longer the partition key for the module.
    media_scope: Mapped[str] = mapped_column(Text, nullable=False, server_default="movie")
    display_order: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")

    watched_folder: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    work_folder: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    output_folder: Mapped[str] = mapped_column(Text, nullable=False, server_default="")

    # Admission. Seeded from what used to be module constants, so an upgrade changes
    # nothing until an operator edits them (ADR-0014 §2).
    media_extensions_csv: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    exclude_markers_csv: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    include_patterns_csv: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    exclude_patterns_csv: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    min_file_size_mb: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    # 0 means no maximum. A nullable column would make "unset" and "zero" the same
    # question at every read site.
    max_file_size_mb: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    min_file_age_seconds: Mapped[int] = mapped_column(Integer, nullable=False, server_default="60")
    exclude_hidden: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="1")
    top_level_only: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="0")

    # Timing.
    scan_interval_seconds: Mapped[int] = mapped_column(Integer, nullable=False, server_default="300")
    hold_minutes: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    # How long a file's size must hold still before it counts as finished being written.
    # This is what replaces guessing at a write duration with an mtime threshold: it
    # observes writing having stopped rather than predicting when it will.
    file_detection_interval_seconds: Mapped[int] = mapped_column(Integer, nullable=False, server_default="30")
    ignore_size_changes: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="0")
    # Filesystem events are the trigger and the periodic scan is the backstop, so this
    # switches off the trigger, never the safety net. Defaults on; a watcher that cannot
    # start degrades to the scan and says so.
    file_system_events_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="1")
    # The read/write probe before queueing. On by default: discovering a file is locked
    # after a job has been enqueued is a failure, discovering it before is a wait.
    skip_access_tests: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="0")
    schedule_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="1")
    schedule_hours_limited: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="0")
    schedule_days: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    # 7x24 at 15-minute resolution, as 672 characters of 0/1. Empty means no restriction,
    # which is what every library has until someone draws a grid. This supersedes the
    # day/start/end trio below, which cannot express "overnight on weeknights, all day at
    # the weekend" — the shape most operators actually want.
    schedule_grid: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    schedule_start: Mapped[str] = mapped_column(Text, nullable=False, server_default="00:00")
    schedule_end: Mapped[str] = mapped_column(Text, nullable=False, server_default="23:59")

    # Capacity.
    max_concurrent_files: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")
    priority: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")

    # A rule set is not owned by a library; deleting one still referenced is refused,
    # so this is RESTRICT rather than CASCADE.
    rule_set_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("refiner_rule_sets.id", ondelete="RESTRICT"), nullable=True
    )

    # Set when the library came from a manager's manifest rather than being typed in
    # (#351). A discovered library stays editable exactly like a manual one.
    discovered_from_connection_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("media_manager_connections.id", ondelete="SET NULL"), nullable=True
    )
    discovered_library_key: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    rule_set: Mapped[RefinerRuleSetRow | None] = relationship(back_populates="libraries")
    manager_links: Mapped[list[RefinerLibraryManagerLinkRow]] = relationship(
        back_populates="library",
        cascade="all, delete-orphan",
        lazy="selectin",
    )


class RefinerLibraryManagerLinkRow(Base):
    """Which media manager connections cover a library.

    A row rather than a column because a library may name more than one — two instances
    of the same product, or one product alongside another mid-migration — and Refiner
    asks all of them (ADR-0014 §4). Multiple is the edge case; the UI defaults to one.
    """

    __tablename__ = "refiner_library_manager_links"
    __table_args__ = (UniqueConstraint("library_id", "connection_id", name="uq_refiner_library_manager_links_pair"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    library_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("refiner_libraries.id", ondelete="CASCADE"), nullable=False
    )
    connection_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("media_manager_connections.id", ondelete="CASCADE"), nullable=False
    )

    library: Mapped[RefinerLibraryRow] = relationship(back_populates="manager_links")
