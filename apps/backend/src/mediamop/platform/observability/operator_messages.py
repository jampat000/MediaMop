"""Plain-language operator messaging for activity and status surfaces."""

from __future__ import annotations

from collections.abc import Mapping

from mediamop.platform.observability.diagnostics import (
    DiagnosticAction,
    DiagnosticModule,
    DiagnosticResult,
    DiagnosticTrigger,
    severity_for_result,
)


PROVIDER_LABELS = {
    "emby": "Emby",
    "jellyfin": "Jellyfin",
    "plex": "Plex",
    "radarr": "Radarr",
    "sonarr": "Sonarr",
}

SCOPE_LABELS = {
    "movie": "Movies",
    "movies": "Movies",
    "tv": "TV episodes",
    "episode": "TV episodes",
}

RESULT_LABELS = {
    DiagnosticResult.FAILED.value: "failed",
    DiagnosticResult.RETRYING.value: "will retry",
    DiagnosticResult.RUNNING.value: "started",
    DiagnosticResult.SKIPPED.value: "skipped",
    DiagnosticResult.SUCCESS.value: "finished",
    DiagnosticResult.WARNING.value: "needs attention",
}


def provider_label(provider: str | None) -> str | None:
    if not provider:
        return None
    value = provider.strip()
    return PROVIDER_LABELS.get(value.lower(), value)


def media_scope_label(media_scope: str | None) -> str | None:
    if not media_scope:
        return None
    value = media_scope.strip()
    return SCOPE_LABELS.get(value.lower(), value)


def count_summary(counts: Mapping[str, int | bool | None]) -> dict[str, int]:
    """Normalize count fields for activity payloads.

    Activity details should expose simple numeric counts with stable keys; this
    keeps dashboard, activity, and tests from inferring meaning from prose.
    """

    out: dict[str, int] = {}
    for key, value in counts.items():
        if value is None or isinstance(value, bool):
            continue
        out[str(key)] = max(0, int(value))
    return out


def activity_detail_envelope(
    *,
    module: DiagnosticModule | str,
    action: DiagnosticAction | str,
    trigger: DiagnosticTrigger | str,
    result: DiagnosticResult | str,
    provider: str | None = None,
    media_scope: str | None = None,
    counts: Mapping[str, int | bool | None] | None = None,
    user_message: str | None = None,
    next_action: str | None = None,
) -> dict[str, object]:
    result_value = str(result)
    payload: dict[str, object] = {
        "module": str(module),
        "action": str(action),
        "trigger": str(trigger),
        "result": result_value,
        "severity": str(severity_for_result(result_value)),
    }
    provider_s = provider_label(provider)
    if provider_s:
        payload["provider"] = provider_s
    scope_s = media_scope_label(media_scope)
    if scope_s:
        payload["media_scope_label"] = scope_s
    if media_scope:
        payload["media_scope"] = media_scope
    if counts:
        payload["counts"] = count_summary(counts)
    if user_message:
        payload["user_message"] = user_message
    if next_action:
        payload["next_action"] = next_action
    return payload


def scan_title(
    *,
    module_label: str,
    result: DiagnosticResult | str,
    count: int,
    scope: str | None,
    source: str | None = None,
    scheduled: bool = False,
) -> str:
    scope_label = media_scope_label(scope) or "items"
    prefix = f"Scheduled {module_label} scan" if scheduled else f"{module_label} scan"
    source_part = f" from {source}" if source else ""
    result_value = str(result)
    if result_value == DiagnosticResult.FAILED.value:
        return f"{prefix} could not check {scope_label}{source_part}"
    if result_value == DiagnosticResult.SKIPPED.value:
        return f"{prefix} skipped {scope_label}{source_part}"
    if count == 0:
        return f"{prefix} found no {scope_label} needing action{source_part}"
    return f"{prefix} found {count} {scope_label} needing action{source_part}"


def connection_test_title(*, module_label: str, name: str, provider: str | None, ok: bool) -> str:
    provider_s = provider_label(provider)
    target = f"{name} ({provider_s})" if provider_s else name
    result = "passed" if ok else "failed"
    return f"{module_label} connection test {result} for {target}"
