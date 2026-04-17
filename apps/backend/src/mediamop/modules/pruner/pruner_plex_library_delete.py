"""Plex library metadata removal used by Pruner Plex **live-only** slice (no preview snapshot).

Operator-facing product language: **Remove broken library entries**. Implementation uses Plex
Media Server's REST API; disk behavior is **not** part of that label.

Verified wire contract (local PMS; ``X-Plex-Token`` auth):

* **HTTP:** ``DELETE {base_url}/library/metadata/{ratingKey}``
* **Headers:** ``X-Plex-Token: <token>`` (same token family as our ``/identity`` ping).
* **What this removes:** The **library metadata row** for that ``ratingKey`` from Plex's library
  database view. Plex may also delete or retain underlying media files depending on **Plex server
  version, library type, and server settings**; MediaMop does **not** guarantee metadata-only
  removal and does **not** promise or deny file deletion — operators must rely on Plex's behavior
  for their server.
* **What we do not claim:** No equivalence to Emby/Jellyfin ``HasPrimaryImage`` / primary-art
  preview semantics; no preview/dry-run for this Plex path.

Return values are for Pruner accounting only, not end-user legal guarantees.
"""

from __future__ import annotations

from mediamop.modules.pruner.pruner_http import http_delete, join_base_path


def plex_delete_library_metadata(*, base_url: str, auth_token: str, rating_key: str) -> tuple[int, str | None]:
    """Call Plex ``DELETE /library/metadata/{ratingKey}``. Returns ``(http_status, body_or_none)``."""

    rk = (rating_key or "").strip()
    if not rk:
        return 0, "empty rating_key"
    headers = {"Accept": "application/json", "X-Plex-Token": auth_token}
    url = join_base_path(base_url, f"library/metadata/{rk}")
    return http_delete(url, headers=headers)
