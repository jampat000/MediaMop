"""The operator's chosen devices, and a file's Direct Play badge for them (#467). Read-only."""

from __future__ import annotations

from pathlib import Path

from sqlalchemy.orm import Session

from mediamop.core.config import MediaMopSettings
from mediamop.modules.refiner.direct_play import (
    OVERRIDE_FILE_NAME,
    DeviceProfile,
    MediaFacts,
    container_for_path,
    evaluate,
    load_device_profiles,
)
from mediamop.modules.refiner.refiner_file_state_model import RefinerFileRow
from mediamop.modules.refiner.schemas_refiner_files import DirectPlayOut
from mediamop.platform.suite_settings.service import ensure_suite_settings_row


def selected_device_ids(session: Session) -> list[str]:
    raw = ensure_suite_settings_row(session).direct_play_devices or ""
    return [part.strip() for part in raw.split(",") if part.strip()]


def save_selected_device_ids(session: Session, settings: MediaMopSettings, selected: list[str]) -> list[str]:
    """Keep only ids the current device list knows, in the list's own order."""

    known = [profile.id for profile in load_device_profiles(settings.mediamop_home)]
    wanted = set(selected)
    kept = [device_id for device_id in known if device_id in wanted]
    ensure_suite_settings_row(session).direct_play_devices = ",".join(kept)
    session.flush()
    return kept


def selected_device_profiles(session: Session, settings: MediaMopSettings) -> tuple[DeviceProfile, ...]:
    chosen = set(selected_device_ids(session))
    if not chosen:
        return ()
    return tuple(p for p in load_device_profiles(settings.mediamop_home) if p.id in chosen)


def device_list_is_customised(settings: MediaMopSettings) -> bool:
    return bool(settings.mediamop_home) and (Path(settings.mediamop_home) / OVERRIDE_FILE_NAME).is_file()


def facts_for_row(row: RefinerFileRow) -> MediaFacts:
    return MediaFacts(
        container=container_for_path(row.relative_path),
        video_codec=row.video_codec,
        video_height=row.video_height,
        video_bit_depth=row.video_bit_depth,
        audio_codecs=tuple(c for c in row.audio_codecs.split(",") if c) if row.audio_codecs is not None else None,
    )


def direct_play_for_row(row: RefinerFileRow, devices: tuple[DeviceProfile, ...]) -> list[DirectPlayOut]:
    if not devices:
        return []
    facts = facts_for_row(row)
    return [
        DirectPlayOut(
            device_id=verdict.device_id,
            device_name=verdict.device_name,
            verdict=verdict.verdict,
            reasons=list(verdict.reasons),
        )
        for verdict in (evaluate(profile, facts) for profile in devices)
    ]
