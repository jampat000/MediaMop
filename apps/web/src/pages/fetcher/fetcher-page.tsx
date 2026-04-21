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
import { fetcherSectionTabClass } from "./fetcher-menu-button";
import { FetcherJobsTab } from "./fetcher-jobs-tab";
import { FetcherOverviewTab } from "./fetcher-overview-tab";
import { mmModuleTabBlurbBandClass, mmModuleTabBlurbTextClass } from "../../lib/ui/mm-module-tab-blurb";

type FetcherPageTabId = "overview" | FetcherArrSettingsTabId | "jobs";

const FETCHER_TAB_BLURBS: Record<FetcherPageTabId, string> = {
  overview: "Check recent Fetcher activity, connection health, and failed-import handling at a glance.",
  connections: "Connect Fetcher to Sonarr and Radarr by saving each server URL and API key.",
  sonarr: "Set how Fetcher searches Sonarr for missing shows and upgrades, including limits and failed-import actions.",
  radarr: "Set how Fetcher searches Radarr for missing movies and upgrades, including limits and failed-import actions.",
  schedules: "Choose when each Fetcher lane runs automatically, including optional day and hour windows.",
  jobs: "View queued, running, and recent Fetcher jobs for troubleshooting and progress tracking.",
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

      <div className="mm-bubble-stack" role="tabpanel" aria-label={tabs.find((t) => t.id === tab)?.label}>
        <div className="mm-bubble-stack min-w-0">
          <div className={mmModuleTabBlurbBandClass} data-testid="fetcher-tab-blurb">
            <p className={mmModuleTabBlurbTextClass}>{FETCHER_TAB_BLURBS[tab]}</p>
          </div>
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
