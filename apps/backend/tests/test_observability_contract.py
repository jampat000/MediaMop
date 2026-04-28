from mediamop.platform.observability.diagnostics import (
    DiagnosticAction,
    DiagnosticEvent,
    DiagnosticModule,
    DiagnosticResult,
    DiagnosticTrigger,
    severity_for_result,
)


def test_diagnostic_event_uses_shared_shape_and_redacts_secret_like_values() -> None:
    event = DiagnosticEvent(
        module=DiagnosticModule.PRUNER,
        action=DiagnosticAction.PREVIEW,
        trigger=DiagnosticTrigger.SCHEDULED,
        result=DiagnosticResult.FAILED,
        severity=severity_for_result(DiagnosticResult.FAILED),
        provider="Jellyfin",
        media_scope="movies",
        correlation_id="job-123",
        reason="Provider returned api_key=abc123 as rejected",
        next_action="Re-enter the Jellyfin API key and run the connection test again.",
        counts={"scanned": 4, "failed": 1},
    )

    assert event.as_safe_dict() == {
        "module": "pruner",
        "action": "preview",
        "trigger": "scheduled",
        "result": "failed",
        "severity": "error",
        "provider": "Jellyfin",
        "media_scope": "movies",
        "correlation_id": "job-123",
        "reason": "Provider returned api_key=[redacted] as rejected",
        "next_action": "Re-enter the Jellyfin API key and run the connection test again.",
        "counts": {"scanned": 4, "failed": 1},
    }


def test_diagnostic_severity_maps_normal_results_to_info() -> None:
    assert severity_for_result(DiagnosticResult.SUCCESS) == "info"
    assert severity_for_result(DiagnosticResult.SKIPPED) == "info"
    assert severity_for_result(DiagnosticResult.RETRYING) == "warning"
    assert severity_for_result(DiagnosticResult.FAILED) == "error"
