"""altHUB Newznab client."""

from __future__ import annotations

from mediamop.modules.broker.broker_client_newznab_base import NewznabClientBase


class BrokerClientAlthub(NewznabClientBase):
    slug = "native__althub"
    protocol = "usenet"
    display_name = "altHUB"
    requires_api_key = True
    default_categories = [2000, 5000]
    default_base_url = "https://lolo.sickbeard.com"
