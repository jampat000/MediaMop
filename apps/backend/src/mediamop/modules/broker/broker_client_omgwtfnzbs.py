"""omgwtfnzbs Newznab client."""

from __future__ import annotations

from mediamop.modules.broker.broker_client_newznab_base import NewznabClientBase


class BrokerClientOmgwtfnzbs(NewznabClientBase):
    slug = "native__omgwtfnzbs"
    protocol = "usenet"
    display_name = "omgwtfnzbs"
    requires_api_key = True
    default_categories = [2000, 5000]
    default_base_url = "https://omgwtfnzbs.me"
