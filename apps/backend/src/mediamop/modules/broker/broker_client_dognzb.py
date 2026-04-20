"""DOGnzb Newznab client."""

from __future__ import annotations

from mediamop.modules.broker.broker_client_newznab_base import NewznabClientBase


class BrokerClientDognzb(NewznabClientBase):
    slug = "native__dognzb"
    protocol = "usenet"
    display_name = "DOGnzb"
    requires_api_key = True
    default_categories = [2000, 5000]
    default_base_url = "https://dognzb.cr"
