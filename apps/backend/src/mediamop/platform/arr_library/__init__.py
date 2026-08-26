"""Credential storage and the legacy settings row for media manager connections.

What used to live here — the Sonarr/Radarr connection routes, their settings service,
and the per-vendor credential resolvers — now lives in
:mod:`mediamop.platform.media_managers`, keyed by kind instead of by product name.

What remains is the encryption used for stored keys, whose KDF domain is frozen for
compatibility with existing installs, and the legacy settings row that migration 0009
copied out of but did not drop.
"""

from __future__ import annotations

from mediamop.platform.arr_library.arr_connection_crypto import (
    decrypt_arr_api_key,
    encrypt_arr_api_key,
    rewrap_arr_api_key,
)
from mediamop.platform.arr_library.arr_operator_settings_repo import ensure_arr_library_operator_settings_row

__all__ = [
    "decrypt_arr_api_key",
    "encrypt_arr_api_key",
    "ensure_arr_library_operator_settings_row",
    "rewrap_arr_api_key",
]
