import { useState } from "react";
import { useMeQuery } from "../../lib/auth/queries";
import { fetcherSectionTabClass } from "../fetcher/fetcher-menu-button";
import { mmModuleTabBlurbBandClass, mmModuleTabBlurbTextClass } from "../../lib/ui/mm-module-tab-blurb";
import { BrokerConnectionsTab } from "./broker-connections-tab";
import {
  BROKER_MODULE_DESCRIPTION,
  BROKER_MODULE_LABEL,
  BROKER_TAB_CONNECTIONS_LABEL,
  BROKER_TAB_INDEXERS_LABEL,
  BROKER_TAB_JOBS_LABEL,
  BROKER_TAB_OVERVIEW_LABEL,
  BROKER_TAB_SEARCH_LABEL,
} from "./broker-display-names";
import { BrokerIndexersTab } from "./broker-indexers-tab";
import { BrokerJobsTab } from "./broker-jobs-tab";
import { BrokerOverviewTab } from "./broker-overview-tab";
import { BrokerSearchTab } from "./broker-search-tab";

type TopTab = "overview" | "connections" | "indexers" | "search" | "jobs";

const BROKER_TAB_BLURBS: Record<TopTab, string> = {
  overview:
    "Indexer health, sync with Sonarr and Radarr, and suggested next steps. Use Connections, Indexers, Search, or Jobs to change credentials, definitions, manual queries, or inspect work.",
  connections:
    "Upstream indexer source plus Sonarr and Radarr endpoints and API keys. Test and save after you change credentials so search and sync keep working.",
  indexers: "Which indexers Broker knows about, how they map into Sonarr and Radarr, and what operators can edit.",
  search: "Run manual torrent or Usenet searches through Broker against your configured indexers.",
  jobs: "Recent Broker jobs — syncs, searches, and failures. Use Activity when you need line-by-line detail.",
};

export function BrokerPage() {
  const me = useMeQuery();
  const canOperate = me.data?.role === "admin" || me.data?.role === "operator";
  const [tab, setTab] = useState<TopTab>("overview");

  const tabs: { id: TopTab; label: string }[] = [
    { id: "overview", label: BROKER_TAB_OVERVIEW_LABEL },
    { id: "connections", label: BROKER_TAB_CONNECTIONS_LABEL },
    { id: "indexers", label: BROKER_TAB_INDEXERS_LABEL },
    { id: "search", label: BROKER_TAB_SEARCH_LABEL },
    { id: "jobs", label: BROKER_TAB_JOBS_LABEL },
  ];

  return (
    <div className="mm-page" data-testid="broker-scope-page">
      <header className="mm-page__intro !mb-0">
        <p className="mm-page__eyebrow">MediaMop</p>
        <h1 className="mm-page__title">{BROKER_MODULE_LABEL}</h1>
        <p className="mm-page__subtitle">{BROKER_MODULE_DESCRIPTION}</p>
      </header>

      <nav
        className="mb-5 mt-3 flex gap-2.5 overflow-x-auto sm:mt-4 sm:flex-wrap sm:overflow-visible"
        data-testid="broker-top-level-tabs"
        aria-label="Broker sections"
      >
        {tabs.map((t) => (
          <button
            key={t.id}
            type="button"
            role="tab"
            aria-selected={tab === t.id}
            className={fetcherSectionTabClass(tab === t.id)}
            onClick={() => setTab(t.id)}
          >
            {t.label}
          </button>
        ))}
      </nav>

      <div className="space-y-5" role="tabpanel">
        <div className={mmModuleTabBlurbBandClass} data-testid="broker-tab-blurb">
          <p className={mmModuleTabBlurbTextClass}>{BROKER_TAB_BLURBS[tab]}</p>
        </div>
        <div className="min-w-0">
          {tab === "overview" ? <BrokerOverviewTab onOpenTab={(t) => setTab(t)} /> : null}
          {tab === "connections" ? <BrokerConnectionsTab canOperate={Boolean(canOperate)} /> : null}
          {tab === "indexers" ? <BrokerIndexersTab canOperate={Boolean(canOperate)} /> : null}
          {tab === "search" ? <BrokerSearchTab /> : null}
          {tab === "jobs" ? <BrokerJobsTab /> : null}
        </div>
      </div>
    </div>
  );
}
