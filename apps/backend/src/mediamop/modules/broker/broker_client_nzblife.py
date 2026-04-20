"""NZB.life Newznab client."""

from __future__ import annotations

from mediamop.modules.broker.broker_client_newznab_base import NewznabClientBase


class BrokerClientNzblife(NewznabClientBase):
    slug = "native__nzblife"
    protocol = "usenet"
    display_name = "NZB.life"
    requires_api_key = True
    default_categories = [2000, 5000]
    default_base_url = "https://nzb.life"
