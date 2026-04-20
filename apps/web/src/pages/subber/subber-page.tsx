import { useState } from "react";
import { fetcherSectionTabClass } from "../fetcher/fetcher-menu-button";
import { useMeQuery } from "../../lib/auth/queries";
import { SubberConnectionsTab } from "./subber-connections-tab";
import { SubberJobsTab } from "./subber-jobs-tab";
import { SubberMoviesTab } from "./subber-movies-tab";
import { SubberOverviewTab } from "./subber-overview-tab";
import { SubberPreferencesTab } from "./subber-preferences-tab";
import { SubberProvidersTab } from "./subber-providers-tab";
import { SubberScheduleTab } from "./subber-schedule-tab";
import { SubberTvTab } from "./subber-tv-tab";

type TopTab = "overview" | "tv" | "movies" | "connections" | "providers" | "preferences" | "schedule" | "jobs";

export function SubberPage() {
  const me = useMeQuery();
  const canOperate = me.data?.role === "admin" || me.data?.role === "operator";
  const [tab, setTab] = useState<TopTab>("overview");

  const tabs: { id: TopTab; label: string }[] = [
    { id: "overview", label: "Overview" },
    { id: "tv", label: "TV" },
    { id: "movies", label: "Movies" },
    { id: "connections", label: "Connections" },
    { id: "providers", label: "Providers" },
    { id: "preferences", label: "Preferences" },
    { id: "schedule", label: "Schedule" },
    { id: "jobs", label: "Jobs" },
  ];

  return (
    <div className="mm-page" data-testid="subber-scope-page">
      <header className="mm-page__intro !mb-0">
        <p className="mm-page__eyebrow">MediaMop</p>
        <h1 className="mm-page__title">Subber</h1>
        <p className="mm-page__subtitle">Automatically find and download subtitles for your movies and TV shows.</p>
      </header>

      <nav
        className="mt-3 flex gap-2.5 overflow-x-auto border-b border-[var(--mm-border)] pb-3.5 sm:mt-4 sm:flex-wrap sm:overflow-visible"
        data-testid="subber-top-level-tabs"
        aria-label="Subber sections"
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

      <div className="mt-6 sm:mt-7" role="tabpanel">
        {tab === "overview" ? (
          <SubberOverviewTab onOpenTab={(t) => setTab(t === "settings" ? "connections" : t)} />
        ) : null}
        {tab === "tv" ? <SubberTvTab canOperate={Boolean(canOperate)} /> : null}
        {tab === "movies" ? <SubberMoviesTab canOperate={Boolean(canOperate)} /> : null}
        {tab === "connections" ? <SubberConnectionsTab canOperate={Boolean(canOperate)} /> : null}
        {tab === "providers" ? <SubberProvidersTab canOperate={Boolean(canOperate)} /> : null}
        {tab === "preferences" ? <SubberPreferencesTab canOperate={Boolean(canOperate)} /> : null}
        {tab === "schedule" ? <SubberScheduleTab canOperate={Boolean(canOperate)} /> : null}
        {tab === "jobs" ? <SubberJobsTab /> : null}
      </div>
    </div>
  );
}
