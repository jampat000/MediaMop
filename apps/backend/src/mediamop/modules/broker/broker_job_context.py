"""Immutable view passed to Broker job handlers after a successful claim."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class BrokerJobWorkContext:
    id: int
    job_kind: str
    payload_json: str | None
    lease_owner: str
