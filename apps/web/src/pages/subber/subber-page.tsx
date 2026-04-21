import { useState } from "react";
import { fetcherSectionTabClass } from "../fetcher/fetcher-menu-button";
import { mmModuleTabBlurbBandClass, mmModuleTabBlurbTextClass } from "../../lib/ui/mm-module-tab-blurb";
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

const SUBBER_TAB_BLURBS: Record<TopTab, string> = {
  overview:
    "Snapshot of subtitle activity, Sonarr and Radarr links, and what to fix next. Use the other tabs to change settings, run searches, or review jobs.",
  tv: "TV episodes from Sonarr with per-language subtitle status. Search for missing tracks when Subber is enabled and your role allows it.",
  movies: "Movies from Radarr with subtitle state. Sync the library or search for missing subtitles when you have permission.",
  connections:
    "OpenSubtitles account, Sonarr and Radarr URLs and API keys, and connection tests. Each block saves on its own action — nothing here writes until you confirm.",
  providers: "Enable providers, set search order, and tune options. Subber only calls providers that are turned on here.",
  preferences: "Default languages and where subtitle files are written. These preferences apply to TV and movie searches going forward.",
  schedule: "Timed scans for missing subtitles on TV and movies, with optional day and time windows.",
  jobs: "Recent subtitle search jobs — outcomes, timing, and errors for troubleshooting. This list is read-only.",
};

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
        className="mb-5 mt-3 flex gap-2.5 overflow-x-auto sm:mt-4 sm:flex-wrap sm:overflow-visible"
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

      <div className="space-y-5" role="tabpanel">
        <div className={mmModuleTabBlurbBandClass} data-testid="subber-tab-blurb">
          <p className={mmModuleTabBlurbTextClass}>{SUBBER_TAB_BLURBS[tab]}</p>
        </div>
        <div className="min-w-0">
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
    </div>
  );
}
