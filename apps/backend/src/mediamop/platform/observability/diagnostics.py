"""Shared diagnostics vocabulary and safe event shaping.

This module enforces the system observability contract at the code boundary:
new activity/log producers should choose values from these enums and pass
operator-readable reasons/next actions instead of raw exception-only messages.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Mapping


SECRET_FIELD_FRAGMENTS = ("api_key", "apikey", "authorization", "cookie", "password", "secret", "token")
SECRET_ASSIGNMENT_RE = re.compile(
    r"(?i)(\b(?:api[_-]?key|authorization|cookie|password|secret|token)\b\s*[:=]\s*)[^,\s;]+",
)


class DiagnosticModule(StrEnum):
    REFINER = "refiner"
    PRUNER = "pruner"
    SUBBER = "subber"
    AUTH = "auth"
    SYSTEM = "system"


class DiagnosticAction(StrEnum):
    APPLY = "apply"
    CLEANUP = "cleanup"
    CONNECTION_TEST = "connection_test"
    IMPORT = "import"
    PREVIEW = "preview"
    REMUX = "remux"
    SCAN = "scan"
    SCHEDULE_RUN = "schedule_run"
    SEARCH = "search"
    SYNC = "sync"
    UPGRADE = "upgrade"


class DiagnosticTrigger(StrEnum):
    MANUAL = "manual"
    RETRY = "retry"
    SCHEDULED = "scheduled"
    STARTUP = "startup"
    SYSTEM = "system"
    WORKER = "worker"


class DiagnosticResult(StrEnum):
    FAILED = "failed"
    RETRYING = "retrying"
    RUNNING = "running"
    SKIPPED = "skipped"
    SUCCESS = "success"
    WARNING = "warning"


class DiagnosticSeverity(StrEnum):
    DEBUG = "debug"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


@dataclass(frozen=True, slots=True)
class DiagnosticEvent:
    module: DiagnosticModule | str
    action: DiagnosticAction | str
    trigger: DiagnosticTrigger | str
    result: DiagnosticResult | str
    severity: DiagnosticSeverity | str
    provider: str | None = None
    media_scope: str | None = None
    correlation_id: str | None = None
    reason: str | None = None
    next_action: str | None = None
    counts: Mapping[str, int] = field(default_factory=dict)

    def as_safe_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "module": str(self.module),
            "action": str(self.action),
            "trigger": str(self.trigger),
            "result": str(self.result),
            "severity": str(self.severity),
        }
        for key in ("provider", "media_scope", "correlation_id", "reason", "next_action"):
            value = getattr(self, key)
            if value:
                payload[key] = sanitize_diagnostic_value(key, value)
        if self.counts:
            payload["counts"] = {str(k): int(v) for k, v in self.counts.items()}
        return payload


def sanitize_diagnostic_value(key: str, value: object) -> object:
    if any(fragment in key.lower() for fragment in SECRET_FIELD_FRAGMENTS):
        return "[redacted]"
    if not isinstance(value, str):
        return value
    return SECRET_ASSIGNMENT_RE.sub(lambda match: f"{match.group(1)}[redacted]", value)


def severity_for_result(result: DiagnosticResult | str) -> DiagnosticSeverity:
    result_value = str(result).lower()
    if result_value == DiagnosticResult.FAILED.value:
        return DiagnosticSeverity.ERROR
    if result_value in {DiagnosticResult.WARNING.value, DiagnosticResult.RETRYING.value}:
        return DiagnosticSeverity.WARNING
    return DiagnosticSeverity.INFO
