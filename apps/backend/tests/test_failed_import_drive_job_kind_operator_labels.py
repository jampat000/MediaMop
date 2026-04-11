"""Operator labels for failed-import drive ``job_kind`` values stay aligned with canonical kinds."""

from __future__ import annotations

from mediamop.modules.fetcher.failed_import_drive_job_kind_operator_labels import (
    OPERATOR_LABEL_BY_FAILED_IMPORT_DRIVE_JOB_KIND,
    operator_label_for_failed_import_drive_job_kind,
)
from mediamop.modules.fetcher.failed_import_drive_job_kinds import FETCHER_FAILED_IMPORT_DRIVE_JOB_KINDS


def test_operator_label_map_covers_exactly_fetcher_drive_job_kinds() -> None:
    assert set(OPERATOR_LABEL_BY_FAILED_IMPORT_DRIVE_JOB_KIND) == FETCHER_FAILED_IMPORT_DRIVE_JOB_KINDS


def test_unknown_job_kind_falls_back_to_raw_string() -> None:
    assert operator_label_for_failed_import_drive_job_kind("some.future.kind.v99") == "some.future.kind.v99"
