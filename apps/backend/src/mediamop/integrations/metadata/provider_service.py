"""Building a provider from the saved connection, and testing it.

The key never leaves this module in plaintext beyond the provider it is handed to, and it
is never returned by the API — the settings response reports only whether one is stored.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from mediamop.core.config import MediaMopSettings
from mediamop.integrations.metadata.provider_port import LookupResult, MetadataProvider
from mediamop.integrations.metadata.tmdb_provider import DEFAULT_TMDB_BASE_URL, TmdbMetadataProvider
from mediamop.platform.arr_library.arr_connection_crypto import decrypt_arr_api_key, encrypt_arr_api_key
from mediamop.platform.suite_settings.model import SuiteSettingsRow

#: The providers MediaMop can talk to. One today; the port exists so the second does not
#: require rewriting the callers.
KNOWN_PROVIDERS: tuple[str, ...] = ("tmdb",)


def store_provider_key(settings: MediaMopSettings, plaintext: str) -> str:
    """Encrypt a key for storage, with the same helper the manager credentials use."""

    return encrypt_arr_api_key(settings, plaintext) if plaintext.strip() else ""


def build_provider(session: Session, settings: MediaMopSettings) -> MetadataProvider | None:
    """The configured provider, or None when there is not one.

    None is a normal outcome, not an error: the provider is optional and every caller
    degrades to the language preference list without it.
    """

    row = session.get(SuiteSettingsRow, 1)
    if row is None:
        return None
    name = (row.metadata_provider or "").strip().lower()
    if name not in KNOWN_PROVIDERS:
        return None
    ciphertext = (row.metadata_provider_key_ciphertext or "").strip()
    key = decrypt_arr_api_key(settings, ciphertext) if ciphertext else ""
    if not key:
        return None
    return TmdbMetadataProvider(
        api_key=key,
        base_url=(row.metadata_provider_base_url or "").strip() or DEFAULT_TMDB_BASE_URL,
    )


def test_provider(session: Session, settings: MediaMopSettings) -> LookupResult:
    """Prove a saved connection works, rather than assuming it."""

    provider = build_provider(session, settings)
    if provider is None:
        return LookupResult(
            status="not_configured",
            detail="No metadata provider is configured, so MediaMop uses the language preferences on each rule set.",
        )
    return provider.test_connection()
