"""Automatic suite configuration snapshot storage and retention."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from mediamop.core.config import MediaMopSettings
from mediamop.platform.configuration_bundle.service import build_configuration_bundle
from mediamop.platform.suite_settings.suite_configuration_backup_model import SuiteConfigurationBackupRow

SUITE_CONFIGURATION_BACKUP_MAX_FILES = 5


def _backup_dir(settings: MediaMopSettings) -> Path:
    return (Path(settings.backup_dir) / "suite-configuration").resolve()


def list_suite_configuration_backups(session: Session, *, settings: MediaMopSettings) -> tuple[str, list[SuiteConfigurationBackupRow]]:
    rows = list(
        session.scalars(
            select(SuiteConfigurationBackupRow).order_by(
                SuiteConfigurationBackupRow.created_at.desc(),
                SuiteConfigurationBackupRow.id.desc(),
            )
        ).all()
    )
    return str(_backup_dir(settings)), rows


def get_suite_configuration_backup_file_path(
    session: Session,
    *,
    settings: MediaMopSettings,
    backup_id: int,
) -> tuple[Path, SuiteConfigurationBackupRow]:
    row = session.get(SuiteConfigurationBackupRow, int(backup_id))
    if row is None:
        raise ValueError("Configuration snapshot not found.")
    if Path(row.file_name).name != row.file_name or not row.file_name.startswith("suite-configuration-"):
        raise ValueError("Configuration snapshot file name is invalid.")
    backup_root = _backup_dir(settings)
    p = (backup_root / row.file_name).resolve()
    try:
        p.relative_to(backup_root)
    except ValueError as exc:
        raise ValueError("Configuration snapshot path is outside the backup directory.") from exc
    if not p.is_file():
        raise ValueError("Configuration snapshot file is missing on disk.")
    return p, row


def create_suite_configuration_backup(session: Session, *, settings: MediaMopSettings) -> SuiteConfigurationBackupRow:
    backup_root = _backup_dir(settings)
    backup_root.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc)
    bundle = build_configuration_bundle(session)
    stamp = now.strftime("%Y%m%d-%H%M%S")
    fname = f"suite-configuration-{stamp}.json"
    fp = backup_root / fname
    i = 1
    while fp.exists():
        fname = f"suite-configuration-{stamp}-{i}.json"
        fp = backup_root / fname
        i += 1
    payload = json.dumps(bundle, indent=2, sort_keys=True).encode("utf-8")
    fp.write_bytes(payload)
    row = SuiteConfigurationBackupRow(file_name=fname, size_bytes=len(payload), created_at=now)
    session.add(row)
    session.flush()
    _prune_old_backups(session, settings=settings)
    return row


def _prune_old_backups(session: Session, *, settings: MediaMopSettings) -> None:
    rows = list(
        session.scalars(
            select(SuiteConfigurationBackupRow).order_by(
                SuiteConfigurationBackupRow.created_at.desc(),
                SuiteConfigurationBackupRow.id.desc(),
            )
        ).all()
    )
    keep = rows[:SUITE_CONFIGURATION_BACKUP_MAX_FILES]
    drop = rows[SUITE_CONFIGURATION_BACKUP_MAX_FILES:]
    if not drop:
        return
    backup_root = _backup_dir(settings)
    keep_names = {r.file_name for r in keep}
    for r in drop:
        try:
            (backup_root / r.file_name).unlink(missing_ok=True)
        except OSError:
            pass
        session.delete(r)
    # Clean up orphan files too.
    if backup_root.is_dir():
        for p in backup_root.glob("suite-configuration-*.json"):
            if p.name not in keep_names:
                try:
                    p.unlink(missing_ok=True)
                except OSError:
                    pass
