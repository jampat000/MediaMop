"""NZBFinder Newznab client."""

from __future__ import annotations

from mediamop.modules.broker.broker_client_newznab_base import NewznabClientBase


class BrokerClientNzbfinder(NewznabClientBase):
    slug = "native__nzbfinder"
    protocol = "usenet"
    display_name = "NZBFinder"
    requires_api_key = True
    default_categories = [2000, 5000]
    default_base_url = "https://nzbfinder.ws"
