"""Indexer fingerprinting for Broker ↔ *arr sync."""

from __future__ import annotations

import hashlib

from sqlalchemy.orm import Session

from mediamop.modules.broker.broker_arr_connections_service import get_connection
from mediamop.modules.broker.broker_indexers_model import BrokerIndexerRow


def compute_indexer_fingerprint(indexers: list[BrokerIndexerRow]) -> str:
    """SHA256 of sorted ``id|slug`` lines for **enabled** indexers only (stable order)."""

    lines = sorted(f"{int(r.id)}|{r.slug}" for r in indexers if int(r.enabled) == 1)
    body = "\n".join(lines).encode("utf-8")
    return hashlib.sha256(body).hexdigest()


def fingerprint_unchanged(session: Session, arr_type: str, current_fingerprint: str) -> bool:
    row = get_connection(session, arr_type)
    prev = (row.indexer_fingerprint or "").strip()
    return prev == current_fingerprint
