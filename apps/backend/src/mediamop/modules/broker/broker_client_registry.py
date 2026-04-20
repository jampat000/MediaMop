"""Registry of native Broker indexer clients + factory for Torznab/Newznab."""

from __future__ import annotations

from mediamop.modules.broker.broker_client_academictorrents import BrokerClientAcademictorrents
from mediamop.modules.broker.broker_client_althub import BrokerClientAlthub
from mediamop.modules.broker.broker_client_animetosho import BrokerClientAnimetosho
from mediamop.modules.broker.broker_client_anidex import BrokerClientAnidex
from mediamop.modules.broker.broker_client_bangumimoe import BrokerClientBangumimoe
from mediamop.modules.broker.broker_client_base import BrokerClientBase
from mediamop.modules.broker.broker_client_binsearch import BrokerClientBinsearch
from mediamop.modules.broker.broker_client_bitsearch import BrokerClientBitsearch
from mediamop.modules.broker.broker_client_bt4g import BrokerClientBt4g
from mediamop.modules.broker.broker_client_dognzb import BrokerClientDognzb
from mediamop.modules.broker.broker_client_drunkenslug import BrokerClientDrunkenslug
from mediamop.modules.broker.broker_client_eztv import BrokerClientEztv
from mediamop.modules.broker.broker_client_ext import BrokerClientExt
from mediamop.modules.broker.broker_client_gingadaddy import BrokerClientGingadaddy
from mediamop.modules.broker.broker_client_internetarchive import BrokerClientInternetarchive
from mediamop.modules.broker.broker_client_knaben import BrokerClientKnaben
from mediamop.modules.broker.broker_client_limetorrents import BrokerClientLimetorrents
from mediamop.modules.broker.broker_client_magnetdl import BrokerClientMagnetdl
from mediamop.modules.broker.broker_client_newznab import BrokerNewznabClient
from mediamop.modules.broker.broker_client_ninjacentral import BrokerClientNinjacentral
from mediamop.modules.broker.broker_client_nyaasukebei import BrokerClientNyaasukebei
from mediamop.modules.broker.broker_client_nyaa import BrokerClientNyaa
from mediamop.modules.broker.broker_client_nzbgeek import BrokerClientNzbgeek
from mediamop.modules.broker.broker_client_nzbindex import BrokerClientNzbindex
from mediamop.modules.broker.broker_client_nzbplanet import BrokerClientNzbplanet
from mediamop.modules.broker.broker_client_nzbcat import BrokerClientNzbcat
from mediamop.modules.broker.broker_client_nzbfinder import BrokerClientNzbfinder
from mediamop.modules.broker.broker_client_nzblife import BrokerClientNzblife
from mediamop.modules.broker.broker_client_omgwtfnzbs import BrokerClientOmgwtfnzbs
from mediamop.modules.broker.broker_client_oznzb import BrokerClientOznzb
from mediamop.modules.broker.broker_client_shanaproject import BrokerClientShanaproject
from mediamop.modules.broker.broker_client_showrss import BrokerClientShowrss
from mediamop.modules.broker.broker_client_snowfl import BrokerClientSnowfl
from mediamop.modules.broker.broker_client_subsplease import BrokerClientSubsplease
from mediamop.modules.broker.broker_client_thepiratebay import BrokerClientThepiratebay
from mediamop.modules.broker.broker_client_tokyotoshokan import BrokerClientTokyotoshokan
from mediamop.modules.broker.broker_client_torlock import BrokerClientTorlock
from mediamop.modules.broker.broker_client_torrentdownload import BrokerClientTorrentdownload
from mediamop.modules.broker.broker_client_torrentdownloads import BrokerClientTorrentdownloads
from mediamop.modules.broker.broker_client_torrentz2 import BrokerClientTorrentz2
from mediamop.modules.broker.broker_client_torznab import BrokerTorznabClient
from mediamop.modules.broker.broker_client_usenetcrawler import BrokerClientUsenetcrawler
from mediamop.modules.broker.broker_client_yts import BrokerClientYts
from mediamop.modules.broker.broker_indexers_model import BrokerIndexerRow

ALL_NATIVE_CLIENTS: list[BrokerClientBase] = [
    BrokerClientAcademictorrents(),
    BrokerClientAlthub(),
    BrokerClientAnimetosho(),
    BrokerClientAnidex(),
    BrokerClientBangumimoe(),
    BrokerClientBinsearch(),
    BrokerClientBitsearch(),
    BrokerClientBt4g(),
    BrokerClientDognzb(),
    BrokerClientDrunkenslug(),
    BrokerClientEztv(),
    BrokerClientExt(),
    BrokerClientGingadaddy(),
    BrokerClientInternetarchive(),
    BrokerClientKnaben(),
    BrokerClientLimetorrents(),
    BrokerClientMagnetdl(),
    BrokerClientNinjacentral(),
    BrokerClientNyaasukebei(),
    BrokerClientNyaa(),
    BrokerClientNzbgeek(),
    BrokerClientNzbindex(),
    BrokerClientNzbplanet(),
    BrokerClientNzbcat(),
    BrokerClientNzbfinder(),
    BrokerClientNzblife(),
    BrokerClientOmgwtfnzbs(),
    BrokerClientOznzb(),
    BrokerClientShanaproject(),
    BrokerClientShowrss(),
    BrokerClientSnowfl(),
    BrokerClientSubsplease(),
    BrokerClientThepiratebay(),
    BrokerClientTokyotoshokan(),
    BrokerClientTorlock(),
    BrokerClientTorrentdownload(),
    BrokerClientTorrentdownloads(),
    BrokerClientTorrentz2(),
    BrokerClientUsenetcrawler(),
    BrokerClientYts(),
]

NATIVE_CLIENT_BY_SLUG: dict[str, BrokerClientBase] = {c.slug: c for c in ALL_NATIVE_CLIENTS}


def get_client_for_indexer(indexer: BrokerIndexerRow) -> BrokerClientBase | None:
    kind = (indexer.kind or "").strip()
    if kind.startswith("native__"):
        return NATIVE_CLIENT_BY_SLUG.get(kind)
    if kind == "torznab":
        return BrokerTorznabClient(
            base_url=indexer.url or "",
            api_key=indexer.api_key or "",
            slug=indexer.slug or "torznab",
        )
    if kind == "newznab":
        return BrokerNewznabClient(
            base_url=indexer.url or "",
            api_key=indexer.api_key or "",
            slug=indexer.slug or "newznab",
        )
    return None
