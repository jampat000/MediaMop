import { useState } from "react";
import { Link } from "react-router-dom";
import { mmSectionTabClass } from "../../lib/ui/mm-control-roles";
import { RefinerProcessSettingsSection } from "./refiner-process-settings-section";
import { RefinerJobsInspectionSection } from "./refiner-jobs-inspection-section";
import {
  RefinerOverviewTab,
  type RefinerOverviewOpenTab,
} from "./refiner-overview-tab";
import { RefinerPathSettingsSection } from "./refiner-path-settings-section";
import { RefinerSchedulesSection } from "./refiner-schedules-section";
import { RefinerRemuxSection } from "./refiner-remux-section";
import {
  mmModuleTabBlurbBandClass,
  mmModuleTabBlurbTextClass,
} from "../../lib/ui/mm-module-tab-blurb";

type RefinerPageTabId =
  | "overview"
  | "libraries"
  | "audio-subtitles"
  | "jobs"
  | "schedules";

const REFINER_TAB_BLURBS: Record<RefinerPageTabId, string> = {
  overview:
    "Review remux throughput, recent outcomes, and overall Refiner status.",
  libraries:
    "Set TV and Movies watched, work, and output folders, plus per-library scan controls.",
  "audio-subtitles":
    "Choose default audio and subtitle remux rules separately for TV and Movies.",
  schedules:
    "Set optional schedule windows and run manual watched-folder scans when needed.",
  jobs: "View queued, running, and recent Refiner jobs for troubleshooting and progress.",
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
          Refiner remuxes <strong className="text-[var(--mm-text)]">TV</strong>{" "}
          and <strong className="text-[var(--mm-text)]">Movies</strong> into the
          audio and subtitle layout you want. Each library stays on its own.
          When jobs finish, details are on{" "}
          <Link
            className="font-semibold text-[var(--mm-text)] underline-offset-2 hover:underline"
            to="/activity"
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
            className={mmSectionTabClass(tab === id)}
            onClick={() => setTab(id)}
          >
            {label}
          </button>
        ))}
      </nav>

      <div
        className="mm-bubble-stack"
        role="tabpanel"
        aria-label={tabs.find((t) => t.id === tab)?.label}
      >
        <div className="mm-bubble-stack w-full min-w-0">
          <div
            className={mmModuleTabBlurbBandClass}
            data-testid="refiner-tab-blurb"
          >
            <p className={mmModuleTabBlurbTextClass}>
              {REFINER_TAB_BLURBS[tab]}
            </p>
          </div>
          {tab === "overview" ? (
            <RefinerOverviewTab onOpenTab={openFromOverview} />
          ) : null}

          {tab === "libraries" ? (
            <div className="mm-bubble-stack flex w-full min-w-0 flex-col">
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
