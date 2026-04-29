from mediamop.platform.observability.diagnostics import DiagnosticAction, DiagnosticModule, DiagnosticResult, DiagnosticTrigger
from mediamop.platform.observability.operator_messages import (
    activity_detail_envelope,
    connection_test_title,
    count_summary,
    media_scope_label,
    provider_label,
    scan_title,
)


def test_operator_message_labels_are_plain_language() -> None:
    assert provider_label("jellyfin") == "Jellyfin"
    assert media_scope_label("tv") == "TV episodes"
    assert scan_title(
        module_label="Pruner preview",
        result=DiagnosticResult.SUCCESS,
        count=2,
        scope="movies",
        source="Living room (Jellyfin)",
        scheduled=True,
    ) == "Scheduled Pruner preview scan found 2 Movies needing action from Living room (Jellyfin)"
    assert connection_test_title(module_label="Pruner", name="Living room", provider="plex", ok=False) == (
        "Pruner connection test failed for Living room (Plex)"
    )


def test_activity_detail_envelope_uses_standard_fields_and_counts() -> None:
    assert activity_detail_envelope(
        module=DiagnosticModule.SUBBER,
        action=DiagnosticAction.SEARCH,
        trigger=DiagnosticTrigger.WORKER,
        result=DiagnosticResult.SKIPPED,
        provider="opensubtitles",
        media_scope="movies",
        counts={"checked": 1, "downloaded": 0, "bad_flag": True},
        user_message="No subtitle was found.",
    ) == {
        "module": "subber",
        "action": "search",
        "trigger": "worker",
        "result": "skipped",
        "severity": "info",
        "provider": "opensubtitles",
        "media_scope_label": "Movies",
        "media_scope": "movies",
        "counts": {"checked": 1, "downloaded": 0},
        "user_message": "No subtitle was found.",
    }


def test_count_summary_never_reports_negative_counts() -> None:
    assert count_summary({"failed": -5, "removed": 3}) == {"failed": 0, "removed": 3}
