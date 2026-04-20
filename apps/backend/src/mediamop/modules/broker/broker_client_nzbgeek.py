"""NZBGeek Newznab client."""

from __future__ import annotations

from mediamop.modules.broker.broker_client_newznab_base import NewznabClientBase


class BrokerClientNzbgeek(NewznabClientBase):
    slug = "native__nzbgeek"
    protocol = "usenet"
    display_name = "NZBGeek"
    requires_api_key = True
    default_categories = [2000, 5000]
    default_base_url = "https://api.nzbgeek.info"
