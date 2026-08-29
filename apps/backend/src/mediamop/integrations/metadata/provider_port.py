"""What MediaMop needs from a metadata provider, stated without naming one.

TMDb is the obvious first provider and the only one implemented. The port exists anyway,
for the same reason the media manager port does: the moment a second provider appears, a
module that talked to the first one directly has to be rewritten rather than reconfigured.

Everything here is **optional and degrading**. A provider that is absent, unreachable, or
simply has no match must never fail a file — Refiner's existing preference list is a
complete answer on its own, and this only ever improves on it.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol

LookupStatus = Literal["matched", "no_match", "not_configured", "unreachable"]


@dataclass(frozen=True, slots=True)
class TitleMetadata:
    """What a provider knows about one title."""

    #: ISO 639-1 as providers report it (``fr``), normalised to 639-2 by the caller.
    original_language: str = ""
    title: str = ""
    year: int | None = None
    provider_id: str = ""

    @property
    def has_original_language(self) -> bool:
        return bool(self.original_language.strip())


@dataclass(frozen=True, slots=True)
class LookupResult:
    """A lookup outcome, including the outcomes that are not answers.

    ``no_match``, ``not_configured`` and ``unreachable`` are deliberately distinct. They
    all fall back to the preference list, but an operator debugging "why did it keep the
    dub" needs to know whether the provider was asked, answered, or never consulted.
    """

    status: LookupStatus
    metadata: TitleMetadata | None = None
    detail: str = ""

    @property
    def matched(self) -> bool:
        return self.status == "matched" and self.metadata is not None


class MetadataProvider(Protocol):
    """One provider. Implementations must never raise."""

    name: str

    def lookup_movie(self, *, title: str, year: int | None) -> LookupResult: ...

    def test_connection(self) -> LookupResult: ...
