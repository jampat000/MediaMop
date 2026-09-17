from mediamop.platform.observability.diagnostics import (
    DiagnosticAction,
    DiagnosticModule,
    DiagnosticResult,
    DiagnosticTrigger,
)
from mediamop.platform.observability.operator_messages import (
    activity_detail_envelope,
    count_summary,
    media_scope_label,
    provider_label,
)


def test_operator_message_labels_are_plain_language() -> None:
    assert provider_label("jellyfin") == "Jellyfin"
    assert media_scope_label("tv") == "TV episodes"


def test_activity_detail_envelope_uses_standard_fields_and_counts() -> None:
    assert activity_detail_envelope(
        module=DiagnosticModule.REFINER,
        action=DiagnosticAction.SEARCH,
        trigger=DiagnosticTrigger.WORKER,
        result=DiagnosticResult.SKIPPED,
        provider="opensubtitles",
        media_scope="movies",
        counts={"checked": 1, "downloaded": 0, "bad_flag": True},
        user_message="No subtitle was found.",
    ) == {
        "module": "refiner",
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
