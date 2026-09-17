"""Black-box processing: what happens when a file cannot be processed.

Covers behaviour the backend tested from the inside in test_refiner_pass_through.py,
test_refiner_reject.py and test_refiner_retry_and_requeue.py: retries, handing the original back,
holding after repeated failures, and rejecting a bad release through Deluno or a Radarr queue.
"""

from __future__ import annotations

from pathlib import Path

from tests.contract.processing import _helpers as h
from tests.contract.support.fake_ffmpeg import fake_media_bytes, probe
from tests.contract.support.polling import wait_until

REMUX_CRASH = "Conversion failed: the fake ffmpeg was told to fail"


def _signed_in_working_server(server_factory, client_factory, fake_ffmpeg):
    server = h.start_working_server(server_factory, fake_ffmpeg)
    admin = client_factory(server)
    admin.ensure_admin()
    return server, admin


def test_failure_is_retried_then_the_original_is_passed_through_unchanged(
    server_factory, client_factory, fake_ffmpeg, fake_managers, tmp_path: Path
) -> None:
    server, admin = _signed_in_working_server(server_factory, client_factory, fake_ffmpeg)
    folders = h.Folders.make(tmp_path)
    fake, library = h.deluno_setup(
        admin, fake_managers, folders, failure_policy="pass_through", max_attempts=2, retry_backoff_seconds=1
    )
    fake_ffmpeg.set_file_rule("film.mkv", remux_error=REMUX_CRASH)
    release = folders.watched / "Broken.Remux.2021"
    release.mkdir()
    source = release / "film.mkv"
    original = fake_media_bytes(probe(audio_languages=("eng", "fre")))
    source.write_bytes(original)
    rel = "Broken.Remux.2021/film.mkv"
    h.detect_without_queueing(admin, library, rel)

    h.post_handoff(admin, handoff_id="handoff-pt-1", source_path=source)

    first = h.wait_for_file_status(admin, library["id"], rel, "processing_failed")
    assert first["failure_class"] == "execution"
    assert first["failure_attempts"] == 1
    assert first["next_retry_at"] is not None
    # A failure that will be retried is not final, so nothing is reported to the manager yet.
    assert h.callbacks(fake, "handoff-pt-1") == []

    # Once the second attempt fails the retries are spent, and the original is handed back.
    h.drive_retries_until(
        admin,
        library,
        lambda: h.handoff_status(admin, "handoff-pt-1")["state"] == "passed-through",
        what="the hand-off to be passed through",
    )

    delivered = folders.output / "Broken.Remux.2021" / "film.mkv"
    assert delivered.read_bytes() == original
    # The source is never deleted by a pass-through.
    assert source.read_bytes() == original
    assert len(fake_ffmpeg.calls(tool="ffmpeg", step="remux")) == 2
    assert [j["status"] for j in h.jobs(admin, kind=h.PASS_THROUGH_KIND)] == ["completed"]
    # No failure report ever reaches the manager: the file was delivered, not lost.
    assert all(report["status"] != "failed" for report in h.callbacks(fake, "handoff-pt-1"))
    row = h.file_state_after_stop(server, library["id"], rel)
    assert row["status"] == "passed_through"
    assert row["failure_attempts"] == 2
    assert "handed the original back unchanged" in row["status_reason"]


def test_three_failures_hold_the_file_and_the_handoff_reads_failed(
    server_factory, client_factory, fake_ffmpeg, fake_managers, tmp_path: Path
) -> None:
    _server, admin = _signed_in_working_server(server_factory, client_factory, fake_ffmpeg)
    folders = h.Folders.make(tmp_path)
    _fake, library = h.deluno_setup(
        admin, fake_managers, folders, failure_policy="hold", max_attempts=10, retry_backoff_seconds=1
    )
    fake_ffmpeg.set_file_rule("film.mkv", remux_error=REMUX_CRASH)
    release = folders.watched / "Always.Broken.2022"
    release.mkdir()
    source = release / "film.mkv"
    source.write_bytes(fake_media_bytes(probe(audio_languages=("eng", "fre"))))
    rel = "Always.Broken.2022/film.mkv"
    h.detect_without_queueing(admin, library, rel)

    h.post_handoff(admin, handoff_id="handoff-held-1", source_path=source)
    row = h.failure_attempts_reach(admin, library, rel, 3)

    assert row["status"] == "on_hold"
    assert row["quarantined"] is True
    assert row["next_retry_at"] is None
    assert "held this file after 3 repeated execution failures" in row["status_reason"]
    status = h.wait_for_handoff_state(admin, "handoff-held-1", "failed")
    assert status["outputPath"] is None
    assert h.jobs(admin, kind=h.PASS_THROUGH_KIND) == []
    assert source.is_file()
    assert len(fake_ffmpeg.calls(tool="ffmpeg", step="remux")) == 3
    # Held means held: another scan does not start it again.
    h.enqueue_scan(admin, library)
    h.never_within(
        lambda: len(fake_ffmpeg.calls(tool="ffmpeg", step="remux")) > 3, seconds=8, what="a fourth remux attempt"
    )


def test_content_rejection_under_reject_policy_reports_rejected_to_deluno_and_removes_the_download(
    server_factory, client_factory, fake_ffmpeg, fake_managers, tmp_path: Path
) -> None:
    _server, admin = _signed_in_working_server(server_factory, client_factory, fake_ffmpeg)
    folders = h.Folders.make(tmp_path)
    fake, library = h.deluno_setup(
        admin,
        fake_managers,
        folders,
        capabilities=["processor-reject-regrab"],
        failure_policy="reject",
    )
    assert library["failure_policy"] == "reject"
    release = folders.watched / "No.Audio.2023"
    release.mkdir()
    source = release / "film.mkv"
    # A video with no audio at all: the release itself is bad.
    source.write_bytes(fake_media_bytes(probe(audio_languages=())))

    h.post_handoff(admin, handoff_id="handoff-reject-1", source_path=source)

    h.wait_for_handoff_state(admin, "handoff-reject-1", "rejected")
    reports = h.callbacks(fake, "handoff-reject-1")
    assert len(reports) == 1
    report = reports[0]
    assert report["status"] == "failed"
    assert report["disposition"] == "rejected"
    assert report["sourceRemoved"] is True
    assert report["failureClass"] == "preflight"
    assert "no retainable audio" in report["message"]
    wait_until(lambda: not source.exists(), timeout_s=30, what="the rejected download to be removed")
    assert fake_ffmpeg.calls(tool="ffmpeg", step="remux") == []
    assert [j for j in h.jobs(admin, kind=h.REJECT_KIND) if j["status"] == "completed"]
    rejected = h.activity(admin, "refiner.file_rejected")
    assert len(rejected) == 1
    assert rejected[0]["title"] == "film.mkv was rejected so a different release can be found"
    assert "accepted that this release is bad" in rejected[0]["detail"]


def test_content_rejection_under_reject_policy_removes_and_blocklists_the_radarr_queue_item(
    server_factory, client_factory, fake_ffmpeg, fake_managers, tmp_path: Path
) -> None:
    _server, admin = _signed_in_working_server(server_factory, client_factory, fake_ffmpeg)
    folders = h.Folders.make(tmp_path)
    radarr = fake_managers("radarr", root_folders=[str(tmp_path / "library")])
    connection = h.create_connection(admin, radarr)
    h.relax_operator_guards(admin)
    library = h.create_library(admin, folders, manager_connection_ids=[connection["id"]], failure_policy="reject")
    download = folders.watched / "Bad.Movie.2019.1080p"
    download.mkdir()
    source = download / "Bad.Movie.2019.1080p.mkv"
    source.write_bytes(fake_media_bytes(probe(video=0, audio_languages=("eng",))))
    radarr.queue.append(
        {
            "id": 4242,
            "downloadId": "SABnzbd_nzo_contract",
            "title": "Bad.Movie.2019.1080p",
            "status": "completed",
            "trackedDownloadState": "importPending",
            "outputPath": str(download),
            "movieId": 7,
        }
    )

    r = admin.post_csrf(
        "/api/v1/refiner/jobs/file-remux-pass/enqueue",
        {"relative_media_path": "Bad.Movie.2019.1080p/Bad.Movie.2019.1080p.mkv", "library_id": library["id"]},
    )
    assert r.status_code == 200, r.text

    deleted = radarr.wait_for_request("DELETE", "/api/v3/queue/4242", timeout_s=60)[0]
    assert deleted.query == {"removeFromClient": ["true"], "blocklist": ["true"]}
    assert deleted.header("X-Api-Key") == radarr.api_key
    assert radarr.queue == []
    wait_until(
        lambda: [j for j in h.jobs(admin, kind=h.REJECT_KIND) if j["status"] == "completed"],
        timeout_s=30,
        what="the reject job to finish",
    )
    # The download client removes the data; Weir deletes nothing itself on this route.
    assert source.is_file()
    rejected = h.activity(admin, "refiner.file_rejected")
    assert len(rejected) == 1
    assert "blocklisted the release" in rejected[0]["detail"]
