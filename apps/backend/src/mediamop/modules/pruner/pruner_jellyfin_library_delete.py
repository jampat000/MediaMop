"""Jellyfin library-item removal used by Pruner apply (Phase 3).

Operator-facing product language: **Remove broken library entries**. Implementation uses
Jellyfin's REST API; disk behavior is **not** part of that label.

Verified contract (Jellyfin 10.8+ style REST, same header family as our preview probes):

* **HTTP:** ``DELETE {base_url}/Items/{itemId}``
* **Headers:** ``X-Emby-Token: <api_key>`` (Jellyfin documents this token header for client auth.)
* **What this removes:** The **library item** for that id (episode or movie row, matching preview
  granularity). Jellyfin may also remove associated media files depending on **server library
  settings** and item type; MediaMop does **not** guarantee only database metadata removal and
  does **not** promise file deletion — operators must rely on Jellyfin's own behavior for their
  server configuration.
* **What we do not do here:** No separate "delete only from DB" API path in this slice; no Plex
  or Emby calls.

Return values are for Pruner accounting only, not end-user legal guarantees.
"""

from __future__ import annotations

from mediamop.modules.pruner.pruner_http import http_delete, join_base_path


def _headers(api_key: str) -> dict[str, str]:
    return {"X-Emby-Token": api_key, "Accept": "application/json"}


def jellyfin_delete_library_item(*, base_url: str, api_key: str, item_id: str) -> tuple[int, str | None]:
    """Call Jellyfin ``DELETE /Items/{itemId}``. Returns ``(http_status, error_snippet_or_none)``."""

    iid = (item_id or "").strip()
    if not iid:
        return 0, "empty item_id"
    url = join_base_path(base_url, f"Items/{iid}")
    return http_delete(url, headers=_headers(api_key))
