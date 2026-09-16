"""The queryable facts about an activity event, read once when it is written (#469).

Activity details are JSON written by many producers. Filtering on them at read time means
``json_extract`` over every row and a different shape per producer, so the facts people filter
by are lifted into columns instead: why it happened (``trigger``), how it went (``result``), which
library and file it concerns, and which run it belongs to.

Nothing is invented. A value the producer did not state and that cannot be read plainly from the
event type stays empty, and an empty value simply does not match a filter — absence of evidence
is not presented as evidence.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

#: ``docs/operator-messaging-standard.md``, plus ``webhook`` and ``folder_change`` (#469).
TRIGGERS: frozenset[str] = frozenset(
    {"manual", "scheduled", "startup", "worker", "retry", "system", "webhook", "folder_change"}
)
RESULTS: frozenset[str] = frozenset({"success", "skipped", "warning", "retrying", "running", "failed"})

# Read from the event type only when the producer did not say. Ordered: the first match wins,
# so "fell_back" is a warning even though the event also completed.
_PERSON_STARTED_PREFIXES: tuple[str, ...] = ("auth.", "system.reconciliation.")

_RESULT_BY_TYPE_WORD: tuple[tuple[str, str], ...] = (
    ("failed", "failed"),
    ("failure", "failed"),
    ("denied", "failed"),
    ("fell_back", "warning"),
    ("skipped", "skipped"),
    ("progress", "running"),
    ("started", "running"),
    ("succeeded", "success"),
    ("completed", "success"),
    ("passed_through", "success"),
    ("rejected", "success"),
    ("reported", "success"),
    ("cancelled", "success"),
)


@dataclass(frozen=True, slots=True)
class ActivityFacts:
    trigger: str | None = None
    result: str | None = None
    library_id: int | None = None
    relative_path: str | None = None
    run_key: str | None = None


def _detail_dict(detail: str | None) -> dict[str, Any] | None:
    text = (detail or "").strip()
    if not text.startswith("{"):
        return None
    try:
        parsed = json.loads(text)
    except ValueError:
        return None
    return parsed if isinstance(parsed, dict) else None


def classify_activity(*, event_type: str, detail: str | None) -> ActivityFacts:
    data = _detail_dict(detail) or {}

    trigger = data.get("trigger")
    trigger = trigger.strip().lower() if isinstance(trigger, str) and trigger.strip().lower() in TRIGGERS else None
    if trigger is None and (event_type or "").startswith(_PERSON_STARTED_PREFIXES):
        # A sign-in, a password change or a repair someone clicked is, by definition, someone's action.
        trigger = "manual"

    result = data.get("result")
    result = result.strip().lower() if isinstance(result, str) and result.strip().lower() in RESULTS else None
    if result is None and data.get("ok") is False:
        result = "failed"
    if result is None:
        lowered = (event_type or "").lower()
        result = next((value for word, value in _RESULT_BY_TYPE_WORD if word in lowered), None)

    library_id = data.get("library_id")
    library_id = library_id if isinstance(library_id, int) and not isinstance(library_id, bool) else None

    relative_path = data.get("relative_media_path")
    relative_path = relative_path.strip()[:2000] if isinstance(relative_path, str) and relative_path.strip() else None

    run_id = data.get("run_id")
    run_key = f"run:{run_id}"[:128] if isinstance(run_id, (str, int)) and str(run_id).strip() else None

    return ActivityFacts(
        trigger=trigger,
        result=result,
        library_id=library_id,
        relative_path=relative_path,
        run_key=run_key,
    )
