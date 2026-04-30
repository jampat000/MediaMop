"""Supported Subber subtitle provider keys and metadata for UI + validation."""

from __future__ import annotations

PROVIDER_OPENSUBTITLES_ORG = "opensubtitles_org"
PROVIDER_OPENSUBTITLES_COM = "opensubtitles_com"
PROVIDER_PODNAPISI = "podnapisi"
PROVIDER_SUBSCENE = "subscene"
PROVIDER_ADDIC7ED = "addic7ed"
PROVIDER_GESTDOWN = "gestdown"
PROVIDER_SUBDL = "subdl"
PROVIDER_SUBSOURCE = "subsource"
PROVIDER_SUBF2M = "subf2m"
PROVIDER_YIFY = "yify"

ALL_PROVIDER_KEYS: tuple[str, ...] = (
    PROVIDER_OPENSUBTITLES_ORG,
    PROVIDER_OPENSUBTITLES_COM,
    PROVIDER_GESTDOWN,
    PROVIDER_SUBDL,
    PROVIDER_SUBSOURCE,
    PROVIDER_SUBF2M,
    PROVIDER_YIFY,
    PROVIDER_PODNAPISI,
    PROVIDER_SUBSCENE,
    PROVIDER_ADDIC7ED,
)

PROVIDER_DISPLAY_NAMES: dict[str, str] = {
    PROVIDER_OPENSUBTITLES_ORG: "OpenSubtitles.org",
    PROVIDER_OPENSUBTITLES_COM: "OpenSubtitles.com",
    PROVIDER_PODNAPISI: "Podnapisi",
    PROVIDER_SUBSCENE: "Subscene",
    PROVIDER_ADDIC7ED: "Addic7ed",
    PROVIDER_GESTDOWN: "Gestdown",
    PROVIDER_SUBDL: "SubDL",
    PROVIDER_SUBSOURCE: "SubSource",
    PROVIDER_SUBF2M: "Subf2m",
    PROVIDER_YIFY: "YifySubtitles",
}

PROVIDER_REQUIRES_ACCOUNT: dict[str, bool] = {
    PROVIDER_OPENSUBTITLES_ORG: True,
    PROVIDER_OPENSUBTITLES_COM: True,
    PROVIDER_PODNAPISI: False,
    PROVIDER_SUBSCENE: False,
    PROVIDER_ADDIC7ED: True,
    PROVIDER_GESTDOWN: False,
    PROVIDER_SUBDL: True,
    PROVIDER_SUBSOURCE: True,
    PROVIDER_SUBF2M: False,
    PROVIDER_YIFY: False,
}

PROVIDER_CREDENTIAL_FIELDS: dict[str, list[str]] = {
    PROVIDER_OPENSUBTITLES_ORG: ["username", "password", "api_key"],
    PROVIDER_OPENSUBTITLES_COM: ["username", "password", "api_key"],
    PROVIDER_PODNAPISI: ["username", "password"],
    PROVIDER_SUBSCENE: [],
    PROVIDER_ADDIC7ED: ["username", "password"],
    PROVIDER_GESTDOWN: [],
    PROVIDER_SUBDL: ["api_key"],
    PROVIDER_SUBSOURCE: ["api_key"],
    PROVIDER_SUBF2M: [],
    PROVIDER_YIFY: [],
}

# Providers restricted to a single media scope.
# Absent from this dict means the provider supports both TV and Movies.
PROVIDER_SCOPE_RESTRICTION: dict[str, str] = {
    PROVIDER_GESTDOWN: "tv",
    PROVIDER_YIFY: "movies",
}

PROVIDER_AVAILABILITY: dict[str, tuple[bool, str | None]] = {
    PROVIDER_SUBSCENE: (False, "Not available in this version."),
    PROVIDER_ADDIC7ED: (False, "Not available in this version."),
}
