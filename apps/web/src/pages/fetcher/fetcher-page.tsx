import { useState } from "react";
import { useMeQuery } from "../../lib/auth/queries";
import {
  FetcherArrOperatorSettingsSection,
  type FetcherArrSettingsTabId,
} from "./fetcher-arr-operator-settings";
import { FetcherFailedImportsEmbedded } from "./fetcher-failed-imports-workspace";
import {
  FETCHER_TAB_JOBS_LABEL,
  FETCHER_TAB_RADARR_LABEL,
  FETCHER_TAB_SCHEDULES_LABEL,
  FETCHER_TAB_SONARR_LABEL,
} from "./fetcher-display-names";
import { mmModuleTabBlurbBandClass, mmModuleTabBlurbTextClass } from "../../lib/ui/mm-module-tab-blurb";
import { fetcherSectionTabClass } from "./fetcher-menu-button";
import { FetcherJobsTab } from "./fetcher-jobs-tab";
import { FetcherOverviewTab } from "./fetcher-overview-tab";

type FetcherPageTabId = "overview" | FetcherArrSettingsTabId | "jobs";

const FETCHER_TAB_BLURBS: Record<FetcherPageTabId, string> = {
  overview:
    "What Fetcher is doing with Sonarr and Radarr, and where to go next. Use Connections, Sonarr, Radarr, or Schedules to change URLs, API keys, lists, and timing.",
  connections: "Sonarr and Radarr base URLs, API keys, and connectivity tests. Save from each card when you change credentials or endpoints.",
  sonarr: "Sonarr lists, quality profiles, and sync behaviour. Failed imports for TV appear below when this tab is open.",
  radarr: "Radarr lists, quality profiles, and sync behaviour. Failed imports for movies appear below when this tab is open.",
  schedules: "When Fetcher talks to Sonarr and Radarr on a timer — intervals and optional windows for automated sync.",
  jobs: "Recent Fetcher jobs: syncs, searches, and errors. Open Activity when you need the full payload for a run.",
};

export function FetcherPage() {
  const me = useMeQuery();
  const [tab, setTab] = useState<FetcherPageTabId>("overview");

  const tabs: { id: FetcherPageTabId; label: string }[] = [
    { id: "overview", label: "Overview" },
    { id: "connections", label: "Connections" },
    { id: "sonarr", label: FETCHER_TAB_SONARR_LABEL },
    { id: "radarr", label: FETCHER_TAB_RADARR_LABEL },
    { id: "schedules", label: FETCHER_TAB_SCHEDULES_LABEL },
    { id: "jobs", label: FETCHER_TAB_JOBS_LABEL },
  ];

  const showArrSection =
    tab === "connections" || tab === "sonarr" || tab === "radarr" || tab === "schedules";

  return (
    <div className="mm-page">
      <header className="mm-page__intro !mb-0">
        <p className="mm-page__eyebrow">MediaMop</p>
        <h1 className="mm-page__title">Fetcher</h1>
        <p className="mm-page__subtitle">
          Fetcher helps you search for missing TV shows and movies, and upgrade existing ones when a better version is
          available.
        </p>
      </header>

      <nav
        className="mb-5 mt-3 flex gap-2.5 overflow-x-auto sm:mt-4 sm:flex-wrap sm:overflow-visible"
        aria-label="Fetcher sections"
        data-testid="fetcher-section-tabs"
      >
        {tabs.map(({ id, label }) => (
          <button
            key={id}
            type="button"
            role="tab"
            aria-selected={tab === id}
            className={fetcherSectionTabClass(tab === id)}
            onClick={() => setTab(id)}
          >
            {label}
          </button>
        ))}
      </nav>

      <div className="space-y-5" role="tabpanel" aria-label={tabs.find((t) => t.id === tab)?.label}>
        <div className={mmModuleTabBlurbBandClass} data-testid="fetcher-tab-blurb">
          <p className={mmModuleTabBlurbTextClass}>{FETCHER_TAB_BLURBS[tab]}</p>
        </div>
        <div className="min-w-0 space-y-6 sm:space-y-7">
          {tab === "overview" ? <FetcherOverviewTab onOpenSection={(target) => setTab(target)} /> : null}

          {showArrSection ? <FetcherArrOperatorSettingsSection role={me.data?.role} activeTab={tab} /> : null}

          {tab === "sonarr" ? <FetcherFailedImportsEmbedded axis="tv" /> : null}
          {tab === "radarr" ? <FetcherFailedImportsEmbedded axis="movies" /> : null}

          {tab === "jobs" ? <FetcherJobsTab /> : null}
        </div>
      </div>
    </div>
  );
}
