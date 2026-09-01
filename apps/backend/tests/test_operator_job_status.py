"""Plain-language translations for persisted background job failures."""

from __future__ import annotations

from mediamop.platform.jobs.operator_job_status import build_job_operator_status


def test_refiner_database_lock_keeps_actionable_guidance_separate_from_diagnostics() -> None:
    technical = "sqlite3.OperationalError: database is locked"

    result = build_job_operator_status(
        module="refiner",
        job_kind="refiner.file.remux_pass.v1",
        status="failed",
        last_error=technical,
        payload_json='{"relative_media_path":"Movie/Film.mkv"}',
    )

    assert result.operator_message == (
        "MediaMop could not save the Refiner result while another local operation was using the database for Film.mkv."
    )
    assert "Files at once" in result.next_action
    assert "database is locked" not in result.operator_message
    assert result.technical_detail == technical


def test_finalize_failure_tells_operator_not_to_run_media_work_twice() -> None:
    result = build_job_operator_status(
        module="refiner",
        job_kind="refiner.file.remux_pass.v1",
        status="handler_ok_finalize_failed",
        last_error="could not commit completed row",
        payload_json='{"relative_media_path":"Movie/Film.mkv"}',
    )

    assert "work completed" in result.operator_message
    assert "Recover result" in result.next_action
    assert "not run the media work again" in result.next_action


def test_file_preflight_failures_explain_the_user_fix() -> None:
    missing = build_job_operator_status(
        module="refiner",
        job_kind="refiner.file.remux_pass.v1",
        status="failed",
        last_error="MediaMop could not find this file under the saved watched folder.",
        payload_json='{"relative_media_path":"Movie/Missing.mkv"}',
    )
    unsupported = build_job_operator_status(
        module="refiner",
        job_kind="refiner.file.remux_pass.v1",
        status="failed",
        last_error="Refiner does not process .txt files in this pass.",
        payload_json='{"relative_media_path":"Movie/notes.txt"}',
    )

    assert "could not find" in missing.operator_message.lower()
    assert "restore the file" in missing.next_action
    assert "supported Refiner media" in unsupported.operator_message
    assert "supported video file" in unsupported.next_action
