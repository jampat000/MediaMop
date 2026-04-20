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

type FetcherPageTabId = "overview" | FetcherArrSettingsTabId | "jobs";

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
        className="mt-3 flex gap-2.5 overflow-x-auto border-b border-[var(--mm-border)] pb-3.5 sm:mt-4 sm:flex-wrap sm:overflow-visible"
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

      <div className="mt-6 space-y-6 sm:mt-7 sm:space-y-7" role="tabpanel" aria-label={tabs.find((t) => t.id === tab)?.label}>
        {tab === "overview" ? <FetcherOverviewTab onOpenSection={(target) => setTab(target)} /> : null}

        {showArrSection ? <FetcherArrOperatorSettingsSection role={me.data?.role} activeTab={tab} /> : null}

        {tab === "sonarr" ? <FetcherFailedImportsEmbedded axis="tv" /> : null}
        {tab === "radarr" ? <FetcherFailedImportsEmbedded axis="movies" /> : null}

        {tab === "jobs" ? <FetcherJobsTab /> : null}
      </div>
    </div>
  );
}
