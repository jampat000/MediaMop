"""Security guardrails for saved configuration snapshot downloads."""

from __future__ import annotations

import pytest

from mediamop.core.config import MediaMopSettings
from mediamop.core.db import create_db_engine, create_session_factory
from mediamop.platform.suite_settings.suite_configuration_backup_model import SuiteConfigurationBackupRow
from mediamop.platform.suite_settings.suite_configuration_backup_service import get_suite_configuration_backup_file_path


def test_configuration_backup_download_rejects_path_traversal_file_name() -> None:
    settings = MediaMopSettings.load()
    factory = create_session_factory(create_db_engine(settings))

    with factory() as db:
        row = SuiteConfigurationBackupRow(file_name="../outside.json", size_bytes=2)
        db.add(row)
        db.commit()
        backup_id = row.id

    with factory() as db:
        with pytest.raises(ValueError, match="file name is invalid"):
            get_suite_configuration_backup_file_path(db, settings=settings, backup_id=backup_id)
