"""DrunkenSlug Newznab client."""

from __future__ import annotations

from mediamop.modules.broker.broker_client_newznab_base import NewznabClientBase


class BrokerClientDrunkenslug(NewznabClientBase):
    slug = "native__drunkenslug"
    protocol = "usenet"
    display_name = "DrunkenSlug"
    requires_api_key = True
    default_categories = [2000, 5000]
    default_base_url = "https://drunkenslug.com"
