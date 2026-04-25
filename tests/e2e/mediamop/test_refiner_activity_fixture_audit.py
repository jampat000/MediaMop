from __future__ import annotations

import json
import os
import re

import pytest
from playwright.sync_api import expect, sync_playwright

from ._helpers import ensure_signed_in, open_sidebar

pytestmark = [
    pytest.mark.mediamop_e2e,
    pytest.mark.skipif(
        os.environ.get("MEDIAMOP_E2E") != "1",
        reason="MediaMop E2E requires MEDIAMOP_E2E=1 (see tests/e2e/mediamop/conftest.py).",
    ),
]


def test_refiner_activity_card_shows_before_after_processing_details(
    mediamop_shell: str,
    seed_activity_event,
) -> None:
    detail = {
        "outcome": "live_output_written",
        "ok": True,
        "media_scope": "movie",
        "relative_media_path": "movies/Example.Movie.2024.mkv",
        "inspected_source_path": r"C:\Media\Movies\Example.Movie.2024.mkv",
        "output_file": r"C:\Media\Movies-Output\Example.Movie.2024.mkv",
        "stream_counts": {"video": 1, "audio": 9, "subtitle": 8},
        "audio_before": "eng DTS-HD MA 5.1; jpn AAC 2.0; spa AC3 5.1; fre AC3 5.1; deu AC3 5.1; ita AC3 5.1; por AC3 5.1; nld AC3 5.1",
        "audio_after": "eng DTS-HD MA 5.1; jpn AAC 2.0",
        "subs_before": "eng full; eng forced; spa full; fre full; deu full; ita full; por full; jpn signs",
        "subs_after": "eng full; eng forced; jpn signs",
        "removed_audio": ["spa AC3 5.1", "fre AC3 5.1", "deu AC3 5.1", "ita AC3 5.1", "por AC3 5.1", "nld AC3 5.1"],
        "removed_subtitles": ["spa full", "fre full", "deu full", "ita full", "por full"],
        "plan_summary": "Video copied. Audio and subtitle tracks trimmed to preferred languages.",
        "remux_required": True,
        "source_size_bytes": 5368709120,
        "output_size_bytes": 4294967296,
        "source_folder_deleted": False,
        "source_folder_skip_reason": "Source folder retained.",
        "movie_output_folder_deleted": False,
        "movie_output_folder_skip_reason": "Output title folder retained.",
        "ffmpeg_argv": ["ffmpeg", "-i", "Example.Movie.2024.mkv", "-map", "0", "Example.Movie.2024.out.mkv"],
    }
    seed_activity_event(
        event_type="refiner.file_remux_pass_completed",
        module="refiner",
        title="Remux finished for Example.Movie.2024.mkv",
        detail=json.dumps(detail),
    )

    base = mediamop_shell.rstrip("/")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        try:
            page = browser.new_page()
            page.set_default_timeout(30_000)

            ensure_signed_in(page, base)
            open_sidebar(page, "Activity")

            expect(page.get_by_role("heading", name="Example.Movie.2024.mkv was processed successfully")).to_be_visible()
            page.get_by_role("button", name="Apply filters", exact=True).click()
            detail_card = page.get_by_test_id("refiner-remux-activity-detail")
            expect(detail_card).to_be_visible()
            expect(detail_card.locator(".mm-activity-remux-detail__tile-label").filter(has_text="Original size")).to_be_visible()
            expect(detail_card.locator(".mm-activity-remux-detail__tile-label").filter(has_text="Final size")).to_be_visible()
            expect(detail_card.locator(".mm-activity-remux-detail__tile-label").filter(has_text="Change")).to_be_visible()
            detail_card.get_by_text("Show track and cleanup details", exact=True).click()
            expect(detail_card.get_by_text("Before", exact=True)).to_be_visible()
            expect(detail_card.get_by_text("After", exact=True)).to_be_visible()
            expect(detail_card.get_by_text("Audio in file", exact=True)).to_be_visible()
            expect(detail_card.get_by_text("Audio kept", exact=True)).to_be_visible()
            expect(detail_card.get_by_text("Audio removed", exact=True)).to_be_visible()
            expect(detail_card.get_by_text("Subtitles in file", exact=True)).to_be_visible()
            expect(detail_card.get_by_text("Subtitles kept", exact=True)).to_be_visible()
            expect(detail_card.get_by_text("Subtitles removed", exact=True)).to_be_visible()
            assert detail_card.get_by_text("nld AC3 5.1", exact=True).count() >= 2
            assert detail_card.get_by_text("por full", exact=True).count() >= 2
            assert detail_card.get_by_text("Show 2 more", exact=True).count() == 0
            expect(detail_card.get_by_text(r"C:\Media\Movies\Example.Movie.2024.mkv", exact=True)).to_be_visible()
            expect(detail_card.get_by_text(r"C:\Media\Movies-Output\Example.Movie.2024.mkv", exact=True)).to_be_visible()
        finally:
            browser.close()
