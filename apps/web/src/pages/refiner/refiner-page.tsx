import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import {
  WorkspacePage,
  WorkspacePanel,
  WorkspaceTabList,
  type WorkspaceTabOption,
} from "../../components/shared/workspace-shell";
import { RefinerDirectPlaySection } from "./refiner-direct-play-section";
import { RefinerProcessSettingsSection } from "./refiner-process-settings-section";
import { RefinerFilesSection } from "./refiner-files-section";
import { RefinerJobsInspectionSection } from "./refiner-jobs-inspection-section";
import {
  RefinerOverviewTab,
  type RefinerOverviewOpenTab,
} from "./refiner-overview-tab";
import { RefinerLibrariesSection } from "./refiner-libraries-section";
import { RefinerMaintenanceSection } from "./refiner-maintenance-section";
import { RefinerSchedulesSection } from "./refiner-schedules-section";
import { RefinerRemuxSection } from "./refiner-remux-section";

type RefinerPageTabId =
  | "overview"
  | "libraries"
  | "audio-subtitles"
  | "files"
  | "jobs"
  | "maintenance"
  | "schedules";

const REFINER_TAB_BLURBS: Record<RefinerPageTabId, string> = {
  overview:
    "Review remux throughput, recent outcomes, and overall Refiner status.",
  libraries:
    "Add and configure Refiner libraries — folders, file types, schedule and guardrails, one set per library.",
  "audio-subtitles":
    "Build reusable audio, subtitle and metadata profiles, then attach the right profile to each library.",
  schedules:
    "Set optional schedule windows and run manual watched-folder scans when needed.",
  files:
    "Every file Refiner has looked at, and why it is or is not being processed.",
  jobs: "View queued, running, and recent Refiner jobs for troubleshooting and progress.",
  maintenance:
    "Housekeeping MediaMop runs on a schedule, and what this instance is configured with. Start one now if you need to.",
};

const REFINER_TABS = [
  { id: "overview", label: "Overview" },
  { id: "libraries", label: "Libraries" },
  { id: "audio-subtitles", label: "Audio & subtitles" },
  { id: "schedules", label: "Schedules" },
  { id: "files", label: "Files" },
  { id: "jobs", label: "Jobs" },
  { id: "maintenance", label: "Maintenance" },
] as const satisfies readonly WorkspaceTabOption<RefinerPageTabId>[];

const REFINER_CAPABILITY_NOTE =
  "Standalone watched-folder remux works after local safety gates. A media manager adds upstream import protection, library discovery, and safe manager-truth-dependent cleanup; no signal is never treated as an empty queue.";

function refinerTabFromQuery(value: string | null): RefinerPageTabId {
  const allowed: RefinerPageTabId[] = [
    "overview",
    "libraries",
    "audio-subtitles",
    "schedules",
    "files",
    "jobs",
    "maintenance",
  ];
  return allowed.includes(value as RefinerPageTabId)
    ? (value as RefinerPageTabId)
    : "overview";
}

export function RefinerPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const [tab, setTab] = useState<RefinerPageTabId>(() =>
    refinerTabFromQuery(searchParams.get("tab")),
  );

  useEffect(() => {
    setTab(refinerTabFromQuery(searchParams.get("tab")));
  }, [searchParams]);

  const selectTab = (next: RefinerPageTabId) => {
    setTab(next);
    const params = new URLSearchParams(searchParams);
    if (next === "overview") params.delete("tab");
    else params.set("tab", next);
    setSearchParams(params, { replace: true });
  };

  const openFromOverview = (target: RefinerOverviewOpenTab) => {
    const map: Record<RefinerOverviewOpenTab, RefinerPageTabId> = {
      libraries: "libraries",
      "audio-subtitles": "audio-subtitles",
      jobs: "jobs",
      schedules: "schedules",
    };
    selectTab(map[target]);
  };

  return (
    <WorkspacePage
      eyebrow="MediaMop"
      title="Refiner"
      dataTestId="refiner-scope-page"
      description={
        <>
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
        </>
      }
    >
      <WorkspaceTabList
        tabs={REFINER_TABS}
        activeId={tab}
        onSelect={selectTab}
        ariaLabel="Refiner sections"
        idPrefix="refiner-tab"
        panelId="refiner-panel"
        dataTestId="refiner-section-tabs"
      />

      <WorkspacePanel
        id="refiner-panel"
        labelledBy={`refiner-tab-${tab}`}
        context={REFINER_TAB_BLURBS[tab]}
        contextTestId="refiner-tab-blurb"
      >
        {tab === "overview" ? (
          <RefinerOverviewTab onOpenTab={openFromOverview} />
        ) : null}

        {tab === "libraries" ? (
          <div className="mm-bubble-stack flex w-full min-w-0 flex-col">
            <p className="max-w-prose text-sm leading-6 text-[var(--mm-text2)]">
              {REFINER_CAPABILITY_NOTE}
            </p>
            <RefinerLibrariesSection />
            <RefinerProcessSettingsSection />
            <RefinerDirectPlaySection />
          </div>
        ) : null}

        {tab === "audio-subtitles" ? <RefinerRemuxSection /> : null}

        {tab === "schedules" ? <RefinerSchedulesSection /> : null}
        {tab === "files" ? <RefinerFilesSection /> : null}
        {tab === "jobs" ? <RefinerJobsInspectionSection /> : null}
        {tab === "maintenance" ? <RefinerMaintenanceSection /> : null}
      </WorkspacePanel>
    </WorkspacePage>
  );
}
