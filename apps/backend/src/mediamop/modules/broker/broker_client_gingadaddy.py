"""GingaDaddy Newznab client."""

from __future__ import annotations

from mediamop.modules.broker.broker_client_newznab_base import NewznabClientBase


class BrokerClientGingadaddy(NewznabClientBase):
    slug = "native__gingadaddy"
    protocol = "usenet"
    display_name = "GingaDaddy"
    requires_api_key = False
    default_categories = [2000, 5000]
    default_base_url = "https://www.gingadaddy.com"
