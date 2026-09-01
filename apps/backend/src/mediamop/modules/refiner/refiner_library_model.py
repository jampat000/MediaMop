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
    # The ordered sorter list, replacing a ranking tuple that lived in source. Empty
    # means the seeded default, which reproduces that tuple exactly — so nothing changes
    # on upgrade until an operator edits the list (#341).
    audio_sorters_json: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    subtitle_sorters_json: Mapped[str] = mapped_column(Text, nullable=False, server_default="")

    # Original-language audio selection. All off by default; first_if_none is a safety
    # net rather than a preference, because plan_remux already refuses to write a file
    # with no audio and none of this may weaken that (#343).
    keep_original_language: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="0")
    original_language_additional_csv: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    original_language_keep_only_first: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="1")
    original_language_first_if_none: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="1")
    original_language_treat_empty_as_original: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="0")

    # Metadata and attachment stripping, all off by default. An embedded poster is an
    # mjpeg video stream, so removing images is a stream decision as well as a metadata
    # one (#342).
    remove_images: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="0")
    remove_attachments: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="0")
    remove_title: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="0")
    remove_language_tags: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="0")
    remove_other_metadata: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="0")

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
    # Optional cleanup for files rejected by the admission rules. It is deliberately
    # file-only: deleting a whole release folder because one sample failed a size rule
    # would turn a convenience into a data-loss trap.
    rejected_file_action: Mapped[str] = mapped_column(Text, nullable=False, server_default="leave")
    min_file_age_seconds: Mapped[int] = mapped_column(Integer, nullable=False, server_default="60")
    # Optional fixed time windows match FileFlows' Created/Modified before/after
    # admission rules. Null means that side of the window is open.
    created_after: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_before: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    modified_after: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    modified_before: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    exclude_hidden: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="1")
    top_level_only: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="0")

    # Output. Which files beside the video travel with it. Empty migrates nothing, which
    # is what every install did before — and what it did *instead* was delete them with
    # the release folder, so the seeded list is the safer direction (#344).
    sidecar_patterns_csv: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=".srt,.ass,.ssa,.sub,.idx,.vtt,.nfo,.jpg,.png"
    )
    preserve_original_timestamps: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="0")
    # What to do when an output already exists at the path about to be written. "replace"
    # is what every install does today, and a collision used to be silent (#349).
    output_collision_policy: Mapped[str] = mapped_column(Text, nullable=False, server_default="replace")

    # Hardware decoding. Off by default, which is exactly what MediaMop does today by not
    # passing the flags. The per-vendor disable list exists because auto-detection picks
    # the wrong device often enough to need an escape hatch (#345).
    hardware_decode_mode: Mapped[str] = mapped_column(Text, nullable=False, server_default="off")
    hardware_device: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    hardware_disabled_vendors_csv: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    ffmpeg_strictness: Mapped[str] = mapped_column(Text, nullable=False, server_default="normal")

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

    # Retry. A file with no retainable audio will still have none in five minutes; an
    # ffmpeg process that died is the same file meeting a different world. The defaults
    # say so, and an operator watching a flaky NAS can say otherwise.
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False, server_default="3")
    retry_backoff_seconds: Mapped[int] = mapped_column(Integer, nullable=False, server_default="300")
    retry_execution_failures: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="1")
    retry_preflight_failures: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="0")

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
