/** Static catalog of native Broker indexer clients (mirrors ``ALL_NATIVE_CLIENTS`` on the server). */

export type BrokerNativeCatalogEntry = {
  slug: string;
  name: string;
  protocol: "torrent" | "usenet";
  /** UI hint: indexers that require an API key are treated as private in badges. */
  privacy: "public" | "private";
  requiresApiKey: boolean;
};

const T: BrokerNativeCatalogEntry["protocol"] = "torrent";
const U: BrokerNativeCatalogEntry["protocol"] = "usenet";

function entry(
  slug: string,
  name: string,
  protocol: BrokerNativeCatalogEntry["protocol"],
  requiresApiKey: boolean,
): BrokerNativeCatalogEntry {
  return {
    slug,
    name,
    protocol,
    requiresApiKey,
    privacy: requiresApiKey ? "private" : "public",
  };
}

/** Torrent clients first (TV-weighted ordering within group is alphabetical by name). */
const TORRENT: BrokerNativeCatalogEntry[] = [
  entry("native__academictorrents", "Academic Torrents", T, false),
  entry("native__animetosho", "AnimeTosho", T, false),
  entry("native__anidex", "AniDex (may be unreliable)", T, false),
  entry("native__bangumimoe", "Bangumi Moe", T, false),
  entry("native__bitsearch", "BitSearch", T, false),
  entry("native__bt4g", "BT4G", T, false),
  entry("native__eztv", "EZTV", T, false),
  entry("native__ext", "EXT", T, false),
  entry("native__internetarchive", "Internet Archive", T, false),
  entry("native__knaben", "Knaben", T, false),
  entry("native__limetorrents", "LimeTorrents", T, false),
  entry("native__magnetdl", "MagnetDL", T, false),
  entry("native__nyaasukebei", "Nyaa Sukebei", T, false),
  entry("native__nyaa", "Nyaa", T, false),
  entry("native__shanaproject", "ShanaProject", T, false),
  entry("native__showrss", "showRSS", T, false),
  entry("native__snowfl", "Snowfl", T, false),
  entry("native__subsplease", "SubsPlease", T, false),
  entry("native__thepiratebay", "The Pirate Bay", T, false),
  entry("native__tokyotoshokan", "Tokyo Toshokan", T, false),
  entry("native__torlock", "TorLock", T, false),
  entry("native__torrentdownload", "TorrentDownload", T, false),
  entry("native__torrentdownloads", "TorrentDownloads", T, false),
  entry("native__torrentz2", "Torrentz2", T, false),
  entry("native__yts", "YTS", T, false),
];

const USENET: BrokerNativeCatalogEntry[] = [
  entry("native__althub", "altHUB", U, true),
  entry("native__binsearch", "Binsearch", U, false),
  entry("native__dognzb", "DOGnzb", U, true),
  entry("native__drunkenslug", "DrunkenSlug", U, true),
  entry("native__gingadaddy", "GingaDaddy", U, false),
  entry("native__ninjacentral", "NinjaCentral", U, true),
  entry("native__nzbgeek", "NZBGeek", U, true),
  entry("native__nzbindex", "NZBIndex", U, false),
  entry("native__nzbplanet", "NZBPlanet", U, true),
  entry("native__nzbcat", "NZB.cat", U, true),
  entry("native__nzbfinder", "NZBFinder", U, true),
  entry("native__nzblife", "NZB.life", U, true),
  entry("native__omgwtfnzbs", "omgwtfnzbs", U, true),
  entry("native__oznzb", "OZnzb", U, true),
  entry("native__usenetcrawler", "Usenet Crawler", U, true),
];

/** All native clients: torrent group, then usenet (TV before movies global rule applies to protocol ordering). */
export const BROKER_NATIVE_INDEXERS: readonly BrokerNativeCatalogEntry[] = [...TORRENT, ...USENET];
