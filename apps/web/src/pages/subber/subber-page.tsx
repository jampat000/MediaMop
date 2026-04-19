import { useState } from "react";
import { fetcherSectionTabClass } from "../fetcher/fetcher-menu-button";
import { useMeQuery } from "../../lib/auth/queries";
import { SubberJobsTab } from "./subber-jobs-tab";
import { SubberMoviesTab } from "./subber-movies-tab";
import { SubberOverviewTab } from "./subber-overview-tab";
import { SubberScheduleTab } from "./subber-schedule-tab";
import { SubberSettingsTab } from "./subber-settings-tab";
import { SubberTvTab } from "./subber-tv-tab";

type TopTab = "overview" | "tv" | "movies" | "settings" | "schedule" | "jobs";

export function SubberPage() {
  const me = useMeQuery();
  const canOperate = me.data?.role === "admin" || me.data?.role === "operator";
  const [tab, setTab] = useState<TopTab>("overview");

  const tabs: { id: TopTab; label: string }[] = [
    { id: "overview", label: "Overview" },
    { id: "tv", label: "TV" },
    { id: "movies", label: "Movies" },
    { id: "settings", label: "Settings" },
    { id: "schedule", label: "Schedule" },
    { id: "jobs", label: "Jobs" },
  ];

  return (
    <div className="mm-page" data-testid="subber-scope-page">
      <header className="mm-page__intro">
        <p className="mm-page__eyebrow">MediaMop</p>
        <h1 className="mm-page__title">Subber</h1>
        <p className="mm-page__subtitle">Automatically find and download subtitles for your movies and TV shows.</p>
      </header>

      <nav className="mt-4 flex flex-wrap gap-2" data-testid="subber-top-level-tabs" aria-label="Subber sections">
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
        {tab === "overview" ? <SubberOverviewTab /> : null}
        {tab === "tv" ? <SubberTvTab canOperate={Boolean(canOperate)} /> : null}
        {tab === "movies" ? <SubberMoviesTab canOperate={Boolean(canOperate)} /> : null}
        {tab === "settings" ? <SubberSettingsTab canOperate={Boolean(canOperate)} /> : null}
        {tab === "schedule" ? <SubberScheduleTab canOperate={Boolean(canOperate)} /> : null}
        {tab === "jobs" ? <SubberJobsTab /> : null}
      </div>
    </div>
  );
}
