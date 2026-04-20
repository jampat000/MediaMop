"""NinjaCentral Newznab client."""

from __future__ import annotations

from mediamop.modules.broker.broker_client_newznab_base import NewznabClientBase


class BrokerClientNinjacentral(NewznabClientBase):
    slug = "native__ninjacentral"
    protocol = "usenet"
    display_name = "NinjaCentral"
    requires_api_key = True
    default_categories = [2000, 5000]
    default_base_url = "https://ninjacentral.co.za"
