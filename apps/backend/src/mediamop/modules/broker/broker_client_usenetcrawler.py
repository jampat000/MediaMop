"""Usenet Crawler Newznab client."""

from __future__ import annotations

from mediamop.modules.broker.broker_client_newznab_base import NewznabClientBase


class BrokerClientUsenetcrawler(NewznabClientBase):
    slug = "native__usenetcrawler"
    protocol = "usenet"
    display_name = "Usenet Crawler"
    requires_api_key = True
    default_categories = [2000, 5000]
    default_base_url = "https://www.usenet-crawler.com"
