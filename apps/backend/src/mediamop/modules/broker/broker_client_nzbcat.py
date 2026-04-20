"""NZB.cat Newznab client."""

from __future__ import annotations

from mediamop.modules.broker.broker_client_newznab_base import NewznabClientBase


class BrokerClientNzbcat(NewznabClientBase):
    slug = "native__nzbcat"
    protocol = "usenet"
    display_name = "NZB.cat"
    requires_api_key = True
    default_categories = [2000, 5000]
    default_base_url = "https://nzb.cat"
