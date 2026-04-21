import { useState } from "react";
import { Link } from "react-router-dom";
import { fetcherSectionTabClass } from "../fetcher/fetcher-menu-button";
import { mmModuleTabBlurbBandClass, mmModuleTabBlurbTextClass } from "../../lib/ui/mm-module-tab-blurb";
import { RefinerProcessSettingsSection } from "./refiner-process-settings-section";
import { RefinerJobsInspectionSection } from "./refiner-jobs-inspection-section";
import { RefinerOverviewTab, type RefinerOverviewOpenTab } from "./refiner-overview-tab";
import { RefinerPathSettingsSection } from "./refiner-path-settings-section";
import { RefinerSchedulesSection } from "./refiner-schedules-section";
import { RefinerRemuxSection } from "./refiner-remux-section";

type RefinerPageTabId = "overview" | "libraries" | "audio-subtitles" | "jobs" | "schedules";

const REFINER_TAB_BLURBS: Record<RefinerPageTabId, string> = {
  overview:
    "Health and next steps across TV and movie libraries. Open Libraries, Audio & subtitles, Schedules, or Jobs to change paths, remux rules, timing, or inspect work.",
  libraries:
    "Watched folders, work and output paths, and per-library processing defaults. Each section saves on its own — confirm before you rely on new paths.",
  "audio-subtitles":
    "How Refiner remuxes audio and subtitle tracks for TV and movies — language order, commentary, and subtitle retention.",
  schedules: "Automatic remux passes: which libraries run, how often, and optional day or time windows.",
  jobs: "Recent Refiner jobs and outcomes in this module. Full technical detail still lives on Activity when you need it.",
};

export function RefinerPage() {
  const [tab, setTab] = useState<RefinerPageTabId>("overview");

  const tabs: { id: RefinerPageTabId; label: string }[] = [
    { id: "overview", label: "Overview" },
    { id: "libraries", label: "Libraries" },
    { id: "audio-subtitles", label: "Audio & subtitles" },
    { id: "schedules", label: "Schedules" },
    { id: "jobs", label: "Jobs" },
  ];

  const openFromOverview = (target: RefinerOverviewOpenTab) => {
    const map: Record<RefinerOverviewOpenTab, RefinerPageTabId> = {
      libraries: "libraries",
      "audio-subtitles": "audio-subtitles",
      jobs: "jobs",
      schedules: "schedules",
    };
    setTab(map[target]);
  };

  return (
    <div className="mm-page w-full min-w-0" data-testid="refiner-scope-page">
      <header className="mm-page__intro !mb-0">
        <p className="mm-page__eyebrow">MediaMop</p>
        <h1 className="mm-page__title">Refiner</h1>
        <p className="mm-page__subtitle">
          Refiner remuxes <strong className="text-[var(--mm-text)]">TV</strong> and{" "}
          <strong className="text-[var(--mm-text)]">Movies</strong> into the audio and subtitle layout you want. Each library
          stays on its own. When jobs finish, details are on{" "}
          <Link
            className="font-semibold text-[var(--mm-text)] underline-offset-2 hover:underline"
            to="/app/activity"
          >
            Activity
          </Link>
          .
        </p>
      </header>

      <nav
        className="mb-5 mt-3 flex gap-2.5 overflow-x-auto sm:mt-4 sm:flex-wrap sm:overflow-visible"
        aria-label="Refiner sections"
        data-testid="refiner-section-tabs"
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
        <div className={mmModuleTabBlurbBandClass} data-testid="refiner-tab-blurb">
          <p className={mmModuleTabBlurbTextClass}>{REFINER_TAB_BLURBS[tab]}</p>
        </div>
        <div className="w-full min-w-0">
          {tab === "overview" ? <RefinerOverviewTab onOpenTab={openFromOverview} /> : null}

          {tab === "libraries" ? (
            <div className="flex w-full min-w-0 flex-col gap-7">
              <RefinerPathSettingsSection />
              <RefinerProcessSettingsSection />
            </div>
          ) : null}

          {tab === "audio-subtitles" ? <RefinerRemuxSection /> : null}

          {tab === "schedules" ? <RefinerSchedulesSection /> : null}
          {tab === "jobs" ? <RefinerJobsInspectionSection /> : null}
        </div>
      </div>
    </div>
  );
}
