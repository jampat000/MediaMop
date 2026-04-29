"""Operator-facing failure message helpers."""

from __future__ import annotations

import socket
from dataclasses import dataclass
from typing import Literal

from mediamop.platform.observability.diagnostics import sanitize_diagnostic_value
from mediamop.platform.observability.operator_messages import provider_label

FailureKind = Literal["auth", "credential", "network", "rate_limit", "validation", "not_found", "internal"]


@dataclass(frozen=True, slots=True)
class OperatorFailure:
    module: str
    action: str
    kind: FailureKind
    recoverable: bool
    message: str
    why: str
    what_happens_next: str
    next_action: str | None = None
    technical_detail: str | None = None

    def as_dict(self) -> dict[str, object]:
        out: dict[str, object] = {
            "failure_kind": self.kind,
            "recoverable": self.recoverable,
            "what_failed": f"{self.module} {self.action}",
            "why": self.why,
            "what_happens_next": self.what_happens_next,
            "user_message": self.message,
        }
        if self.next_action:
            out["next_action"] = self.next_action
        if self.technical_detail:
            out["technical_detail"] = self.technical_detail
        return out


def classify_exception(exc: BaseException) -> FailureKind:
    text = f"{type(exc).__name__}: {exc}".lower()
    if "rate limit" in text or "ratelimit" in text or "rate-limit" in text or "429" in text:
        return "rate_limit"
    if "credential" in text or "api key" in text or "token" in text or "secret" in text:
        return "credential"
    if "unauthorized" in text or "forbidden" in text or "401" in text or "403" in text:
        return "auth"
    if "not found" in text or "404" in text:
        return "not_found"
    if isinstance(exc, (ConnectionError, TimeoutError, socket.timeout, OSError)):
        return "network"
    if isinstance(exc, (ValueError, TypeError)):
        return "validation"
    return "internal"


def _why_for_kind(kind: FailureKind, *, provider: str | None) -> str:
    where = f" from {provider_label(provider)}" if provider else ""
    if kind == "rate_limit":
        return f"The provider{where} temporarily limited requests."
    if kind == "credential":
        return f"MediaMop could not use the saved credentials{where}."
    if kind == "auth":
        return f"The service{where} rejected the credentials or permission level."
    if kind == "network":
        return f"MediaMop could not reach the service{where} over the network."
    if kind == "validation":
        return "The saved settings or job payload did not pass validation."
    if kind == "not_found":
        return f"The item or endpoint{where} was not found."
    return "The job hit an unexpected error."


def _next_action_for_kind(kind: FailureKind, *, provider: str | None, recoverable: bool) -> str | None:
    provider_s = provider_label(provider) or "the provider"
    if kind in {"credential", "auth"}:
        return f"Re-enter the {provider_s} credentials and run the connection test again."
    if kind == "network":
        return f"Check the {provider_s} address, network access, and that the service is running."
    if kind == "rate_limit":
        return "Wait for the provider limit to reset, or reduce how often this workflow runs."
    if kind == "validation":
        return "Review the saved settings for this workflow and save them again."
    if kind == "not_found" and not recoverable:
        return "Refresh the source library and run the workflow again."
    return None


def operator_failure_from_exception(
    *,
    module: str,
    action: str,
    exc: BaseException,
    provider: str | None = None,
    recoverable: bool = False,
    continuation: str | None = None,
) -> OperatorFailure:
    kind = classify_exception(exc)
    provider_s = provider_label(provider)
    where = f" for {provider_s}" if provider_s else ""
    state = "skipped and continued" if recoverable else "failed"
    happens_next = continuation or (
        "MediaMop will continue with the next available provider."
        if recoverable
        else "This job is marked failed so it does not look successful."
    )
    message = f"{module} {action}{where} {state}: {_why_for_kind(kind, provider=provider)} {happens_next}"
    detail = sanitize_diagnostic_value("technical_detail", f"{type(exc).__name__}: {exc}")
    return OperatorFailure(
        module=module,
        action=action,
        kind=kind,
        recoverable=recoverable,
        message=message,
        why=_why_for_kind(kind, provider=provider),
        what_happens_next=happens_next,
        next_action=_next_action_for_kind(kind, provider=provider, recoverable=recoverable),
        technical_detail=str(detail)[:1000],
    )
