import { useState } from "react";
import { mmSectionTabClass } from "../../lib/ui/mm-control-roles";
import { useMeQuery } from "../../lib/auth/queries";
import { SubberConnectionsTab } from "./subber-connections-tab";
import { SubberJobsTab } from "./subber-jobs-tab";
import { SubberMoviesTab } from "./subber-movies-tab";
import { SubberOverviewTab } from "./subber-overview-tab";
import { SubberPreferencesTab } from "./subber-preferences-tab";
import { SubberProvidersTab } from "./subber-providers-tab";
import { SubberScheduleTab } from "./subber-schedule-tab";
import { SubberTvTab } from "./subber-tv-tab";
import { mmModuleTabBlurbBandClass, mmModuleTabBlurbTextClass } from "../../lib/ui/mm-module-tab-blurb";

type TopTab = "overview" | "tv" | "movies" | "connections" | "providers" | "preferences" | "schedule" | "jobs";

const SUBBER_TAB_BLURBS: Record<TopTab, string> = {
  overview: "Review subtitle coverage, provider status, and recent Subber activity.",
  tv: "Review tracked TV episodes, subtitle coverage, and run TV subtitle searches when needed.",
  movies: "Review tracked movies, subtitle coverage, and run movie subtitle searches when needed.",
  connections: "Save and test the service connections and credentials Subber depends on.",
  providers:
    "Choose which subtitle sources Subber uses and the order it tries them (lower number = searched first). Open a row to set credentials, enable a source, or test it—keep at least one provider on.",
  preferences: "Set subtitle language, matching, and selection behavior for downloads.",
  schedule: "Control automatic subtitle scan timing for TV and Movies, including optional windows.",
  jobs: "View queued, running, and recent Subber jobs.",
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
            className={mmSectionTabClass(tab === t.id)}
            onClick={() => setTab(t.id)}
          >
            {t.label}
          </button>
        ))}
      </nav>

      <div className="mm-bubble-stack" role="tabpanel">
        <div className="mm-bubble-stack min-w-0">
          <div className={mmModuleTabBlurbBandClass} data-testid="subber-tab-blurb">
            <p className={mmModuleTabBlurbTextClass}>{SUBBER_TAB_BLURBS[tab]}</p>
          </div>
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
