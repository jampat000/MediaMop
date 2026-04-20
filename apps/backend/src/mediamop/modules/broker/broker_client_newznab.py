"""Generic Newznab JSON client for arbitrary Newznab indexers."""

from __future__ import annotations

from mediamop.modules.broker.broker_client_newznab_base import NewznabClientBase
from mediamop.modules.broker.broker_result import BrokerResult


class BrokerNewznabClient(NewznabClientBase):
    """Per-indexer Newznab instance (``kind == \"newznab\"``)."""

    protocol = "usenet"
    display_name = "Newznab"
    requires_api_key = False
    default_categories = [2000, 5000]
    default_base_url = ""

    def __init__(self, base_url: str, api_key: str = "", slug: str = "newznab") -> None:
        self._inst_base = (base_url or "").strip().rstrip("/")
        self._inst_key = api_key or ""
        self._inst_slug = slug or "newznab"

    @property
    def slug(self) -> str:
        return self._inst_slug

    def _effective_base(self, base_url: str) -> str:
        return (base_url or self._inst_base or "").strip().rstrip("/")

    async def search(
        self,
        query: str,
        categories: list[int],
        limit: int = 50,
        api_key: str = "",
        base_url: str = "",
    ) -> list[BrokerResult]:
        b = self._effective_base(base_url)
        key = api_key or self._inst_key
        cats = categories if categories else list(self.default_categories)
        return await self._newznab_search(b, key, query, cats, limit, indexer_slug=self._inst_slug)

    async def test(self, api_key: str = "", base_url: str = "") -> bool:
        b = self._effective_base(base_url)
        key = api_key or self._inst_key
        return await self._newznab_test(b, key)
