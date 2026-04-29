from mediamop.platform.observability.failure_messages import classify_exception, operator_failure_from_exception


def test_failure_message_maps_credentials_to_actionable_guidance() -> None:
    failure = operator_failure_from_exception(
        module="Pruner",
        action="connection test",
        provider="jellyfin",
        exc=RuntimeError("api_key=secret was rejected"),
        recoverable=False,
    )

    assert failure.kind == "credential"
    assert failure.recoverable is False
    assert "Pruner connection test for Jellyfin failed" in failure.message
    assert "Re-enter the Jellyfin credentials" in (failure.next_action or "")
    assert "api_key=[redacted]" in (failure.technical_detail or "")


def test_failure_message_marks_rate_limits_as_recoverable() -> None:
    failure = operator_failure_from_exception(
        module="Subber",
        action="subtitle search",
        provider="opensubtitles_com",
        exc=RuntimeError("HTTP 429 rate limit"),
        recoverable=True,
    )

    assert classify_exception(RuntimeError("HTTP 429 rate limit")) == "rate_limit"
    assert failure.recoverable is True
    assert failure.kind == "rate_limit"
    assert "skipped and continued" in failure.message
    assert "continue with the next available provider" in failure.what_happens_next
