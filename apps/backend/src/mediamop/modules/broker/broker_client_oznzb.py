"""OZnzb Newznab client."""

from __future__ import annotations

from mediamop.modules.broker.broker_client_newznab_base import NewznabClientBase


class BrokerClientOznzb(NewznabClientBase):
    slug = "native__oznzb"
    protocol = "usenet"
    display_name = "OZnzb"
    requires_api_key = True
    default_categories = [2000, 5000]
    default_base_url = "https://oznzb.com"
