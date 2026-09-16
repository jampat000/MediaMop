"""Every Activity entry says why it happened, and how it went, in the shared vocabulary (#469).

The trigger is known only where work is queued, so it rides on the job and is copied into the
events the job writes. These pin the carrying and the wording at the points an operator reads.
"""

from __future__ import annotations

import json

from mediamop.modules.refiner.file_remux_pass.visibility import clip_remux_pass_payload_for_activity
from mediamop.modules.refiner.refiner_failure_cleanup_activity import record_refiner_failure_cleanup_sweep_completed
from mediamop.modules.refiner.refiner_work_temp_stale_sweep_activity import (
    record_refiner_work_temp_stale_sweep_completed,
)
from mediamop.platform.activity.classify import classify_activity
from mediamop.platform.activity.provenance import SCAN_TRIGGER_TO_TRIGGER, job_provenance, with_provenance
from mediamop.platform.media_managers.completion_callback import HandoffReportDelivery, HandoffReportTarget
from mediamop.platform.media_managers.manager_port import ManagerConnection

# --- carrying it ---------------------------------------------------------------------------------------


def test_only_a_known_trigger_and_a_real_run_are_carried() -> None:
    assert job_provenance({"trigger": "Webhook", "run_id": "scan-4"}) == {"trigger": "webhook", "run_id": "scan-4"}
    assert job_provenance({"trigger": "because", "run_id": True}) == {}
    assert job_provenance("not a payload") == {}


def test_a_detail_keeps_what_it_already_says() -> None:
    assert with_provenance({"trigger": "worker", "x": 1}, {"trigger": "manual", "run_id": 7}) == {
        "trigger": "worker",
        "run_id": 7,
        "x": 1,
    }


def test_a_scans_own_words_map_onto_the_shared_ones() -> None:
    assert SCAN_TRIGGER_TO_TRIGGER == {"manual": "manual", "periodic": "scheduled", "filesystem_event": "folder_change"}


# --- the remux pass ---------------------------------------------------------------------------------------


def test_a_pass_reports_the_trigger_it_was_queued_with() -> None:
    out = clip_remux_pass_payload_for_activity(
        {"ok": True, "outcome": "live_output_written", "relative_media_path": "a.mkv", "trigger": "webhook"}
    )
    assert out["trigger"] == "webhook"
    assert out["result"] == "success"


def test_a_pass_queued_before_triggers_existed_still_says_worker() -> None:
    assert clip_remux_pass_payload_for_activity({"ok": True, "outcome": "live_output_written"})["trigger"] == "worker"


def test_a_failure_that_will_be_retried_is_retrying_not_failed() -> None:
    out = clip_remux_pass_payload_for_activity(
        {"ok": False, "outcome": "failed_during_execution", "reason": "OSError: [Errno 5]", "retry_scheduled": True}
    )
    assert out["result"] == "retrying"
    assert "next_action" not in out


def test_a_final_failure_offers_an_action_rather_than_the_raw_error() -> None:
    out = clip_remux_pass_payload_for_activity(
        {"ok": False, "outcome": "failed_during_execution", "reason": "OSError: [Errno 5] Input/output error"}
    )
    assert out["result"] == "failed"
    assert "Errno" not in out["next_action"]
    assert "Try again" in out["next_action"]
    assert out["reason"] == "OSError: [Errno 5] Input/output error"


def test_a_failure_being_handed_back_asks_nothing_of_the_operator() -> None:
    out = clip_remux_pass_payload_for_activity(
        {"ok": False, "outcome": "failed_during_execution", "reason": "x", "pass_through_queued": True}
    )
    assert "next_action" not in out


# --- sweeps ----------------------------------------------------------------------------------------------------


class _Session:
    """Just enough of a session for an Activity write: it keeps what was added."""

    def __init__(self) -> None:
        self.info: dict = {}
        self.rows: list = []

    def add(self, row) -> None:  # type: ignore[no-untyped-def]
        row.id = len(self.rows) + 1
        self.rows.append(row)

    def flush(self) -> None:
        pass


def _written(write) -> dict:  # type: ignore[no-untyped-def]
    session = _Session()
    write(session)
    row = session.rows[-1]
    return {"title": row.title, "detail": json.loads(row.detail or "{}")}


def test_a_cleanup_that_found_nothing_says_no_changes_needed_and_why_it_ran() -> None:
    event = _written(
        lambda db: record_refiner_failure_cleanup_sweep_completed(
            db,
            media_scope="tv",
            detail=json.dumps({"cleanup_run_status": "no_eligible_files"}, separators=(",", ":")),
            trigger="manual",
        ),
    )
    assert event["title"] == "Refiner cleanup checked TV: no changes needed"
    assert (event["detail"]["result"], event["detail"]["trigger"]) == ("success", "manual")


def test_a_temp_sweep_that_stood_down_is_skipped_not_success() -> None:
    event = _written(
        lambda db: record_refiner_work_temp_stale_sweep_completed(
            db,
            media_scope="movie",
            detail=json.dumps({"temp_cleanup_ran": False, "temp_cleanup_skipped_reason": "A pass is running."}),
            trigger="scheduled",
        ),
    )
    assert event["title"] == "Refiner left Movies work files alone"
    assert (event["detail"]["result"], event["detail"]["trigger"]) == ("skipped", "scheduled")


# --- hand-off reports -------------------------------------------------------------------------------------------


def test_a_report_the_manager_did_not_accept_is_a_failure_with_something_to_check() -> None:
    from mediamop.platform.media_managers.completion_callback import record_handoff_report

    target = HandoffReportTarget(
        connection=ManagerConnection(kind="deluno", name="Deluno", base_url="http://x", api_key="k"),
        url="http://x/cb",
        headers={},
    )
    event = _written(
        lambda db: record_handoff_report(
            db,
            target=target,
            body={"status": "completed", "releaseName": "Heat"},
            delivery=HandoffReportDelivery(False, "failed: could not reach Deluno"),
            relative_path="Heat/heat.mkv",
        ),
    )
    assert event["detail"]["result"] == "failed"
    assert "Media managers settings page" in event["detail"]["next_action"]
    assert "Error" not in event["detail"]["delivery"]


# --- a person's own actions ---------------------------------------------------------------------------------------


def test_sign_ins_and_account_changes_are_manual() -> None:
    assert classify_activity(event_type="auth.login_succeeded", detail=None).trigger == "manual"
    assert classify_activity(event_type="auth.username_changed", detail="Signed in as bob.").trigger == "manual"
    assert classify_activity(event_type="refiner.file_passed_through", detail=None).trigger is None
