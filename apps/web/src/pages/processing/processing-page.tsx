import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import type { ProcessingFileStatus } from "../../lib/processing/files-api";
import {
  WorkspacePage,
  WorkspacePanel,
  WorkspaceTabList,
  type WorkspaceTabOption,
} from "../../components/shared/workspace-shell";
import { ProcessingDirectPlaySection } from "./processing-direct-play-section";
import { ProcessingProcessSettingsSection } from "./processing-process-settings-section";
import { ProcessingFilesSection } from "./processing-files-section";
import { ProcessingJobsInspectionSection } from "./processing-jobs-inspection-section";
import {
  ProcessingOverviewTab,
  type ProcessingOverviewOpenTab,
} from "./processing-overview-tab";
import { ProcessingLibrariesSection } from "./processing-libraries-section";
import { ProcessingLibrarySection } from "./processing-library-section";
import { ProcessingMaintenanceSection } from "./processing-maintenance-section";
import { ProcessingSchedulesSection } from "./processing-schedules-section";
import { ProcessingRemuxSection } from "./processing-remux-section";

type ProcessingPageTabId =
  | "overview"
  | "libraries"
  | "audio-subtitles"
  | "files"
  | "library"
  | "jobs"
  | "maintenance"
  | "schedules";

const PROCESSING_TAB_BLURBS: Record<ProcessingPageTabId, string> = {
  overview:
    "What needs you, how processing is going, and every library at a glance.",
  libraries:
    "Add and configure libraries: folders, file types, schedule and guardrails, one set per library.",
  "audio-subtitles":
    "Build reusable audio, subtitle and metadata profiles, then attach the right profile to each library.",
  schedules:
    "Set optional schedule windows and run manual watched-folder scans when needed.",
  files:
    "Every file Weir has looked at, and why it is or is not being processed.",
  library:
    "What your library holds and the state of it, and cleaning files that are already in it, in place, with the library's own rules. Separate from new downloads.",
  jobs: "Queued, running and recent jobs, for troubleshooting and progress.",
  maintenance:
    "Housekeeping Weir runs on a schedule, and what this instance is configured with. Start one now if you need to.",
};

const PROCESSING_TABS = [
  { id: "overview", label: "Overview" },
  { id: "libraries", label: "Libraries" },
  { id: "audio-subtitles", label: "Audio & subtitles" },
  { id: "schedules", label: "Schedules" },
  { id: "files", label: "Files" },
  { id: "library", label: "Library" },
  { id: "jobs", label: "Jobs" },
  { id: "maintenance", label: "Maintenance" },
] as const satisfies readonly WorkspaceTabOption<ProcessingPageTabId>[];

const PROCESSING_CAPABILITY_NOTE =
  "A library works on its own once its folders are set. Linking a media manager adds import protection, library discovery and safe cleanup; if the manager does not answer, Weir waits rather than assuming its queue is empty.";

/**
 * Query values that used to name a tab and still turn up in a bookmark or a link someone shared. Issue #568
 * renamed "Existing library" to **Library**; the tab's own id was already `library`, but the label was the
 * visible name, so these spellings are redirected rather than silently dropping the reader on Overview.
 */
const RETIRED_PROCESSING_TAB_VALUES: Record<string, ProcessingPageTabId> = {
  "existing-library": "library",
  existing_library: "library",
  "existing library": "library",
};

function processingTabFromQuery(value: string | null): ProcessingPageTabId {
  const allowed: ProcessingPageTabId[] = [
    "overview",
    "libraries",
    "audio-subtitles",
    "schedules",
    "files",
    "library",
    "jobs",
    "maintenance",
  ];
  if (allowed.includes(value as ProcessingPageTabId)) {
    return value as ProcessingPageTabId;
  }
  return (
    RETIRED_PROCESSING_TAB_VALUES[(value ?? "").toLowerCase()] ?? "overview"
  );
}

export function ProcessingPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const [tab, setTab] = useState<ProcessingPageTabId>(() =>
    processingTabFromQuery(searchParams.get("tab")),
  );

  useEffect(() => {
    const raw = searchParams.get("tab");
    const resolved = processingTabFromQuery(raw);
    setTab(resolved);
    // An old anchor lands on the right tab and then gets the current spelling in the address bar, so the
    // next copy of the link is the new one.
    if (
      raw !== null &&
      raw !== resolved &&
      raw.toLowerCase() in RETIRED_PROCESSING_TAB_VALUES
    ) {
      const params = new URLSearchParams(searchParams);
      params.set("tab", resolved);
      setSearchParams(params, { replace: true });
    }
  }, [searchParams, setSearchParams]);

  const selectTab = (
    next: ProcessingPageTabId,
    fileStatus?: ProcessingFileStatus,
  ) => {
    setTab(next);
    const params = new URLSearchParams(searchParams);
    if (next === "overview") params.delete("tab");
    else params.set("tab", next);
    // The Files tab reads `?status=` on mount, so a lead-band segment can hand it a
    // filter. Any other tab drops a stale filter rather than carrying it around.
    if (next === "files" && fileStatus) params.set("status", fileStatus);
    else params.delete("status");
    setSearchParams(params, { replace: true });
  };

  const openFromOverview = (
    target: ProcessingOverviewOpenTab,
    fileStatus?: ProcessingFileStatus,
  ) => {
    const map: Record<ProcessingOverviewOpenTab, ProcessingPageTabId> = {
      libraries: "libraries",
      "audio-subtitles": "audio-subtitles",
      jobs: "jobs",
      schedules: "schedules",
      files: "files",
    };
    selectTab(map[target], fileStatus);
  };

  return (
    <WorkspacePage
      title="Processing"
      dataTestId="processing-scope-page"
      description={
        <>
          Weir keeps the audio and subtitle tracks you want in each download and
          removes the rest, library by library. Finished work shows on{" "}
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
        tabs={PROCESSING_TABS}
        activeId={tab}
        onSelect={selectTab}
        ariaLabel="Processing sections"
        idPrefix="processing-tab"
        panelId="processing-panel"
        dataTestId="processing-section-tabs"
      />

      <WorkspacePanel
        id="processing-panel"
        labelledBy={`processing-tab-${tab}`}
        context={PROCESSING_TAB_BLURBS[tab]}
        contextTestId="processing-tab-blurb"
      >
        {tab === "overview" ? (
          <ProcessingOverviewTab onOpenTab={openFromOverview} />
        ) : null}

        {tab === "libraries" ? (
          <div className="mm-bubble-stack flex w-full min-w-0 flex-col">
            <p className="max-w-prose text-sm leading-6 text-[var(--mm-text2)]">
              {PROCESSING_CAPABILITY_NOTE}
            </p>
            <ProcessingLibrariesSection />
            <ProcessingProcessSettingsSection />
            <ProcessingDirectPlaySection />
          </div>
        ) : null}

        {tab === "audio-subtitles" ? <ProcessingRemuxSection /> : null}

        {tab === "schedules" ? <ProcessingSchedulesSection /> : null}
        {tab === "files" ? <ProcessingFilesSection /> : null}
        {tab === "library" ? <ProcessingLibrarySection /> : null}
        {tab === "jobs" ? <ProcessingJobsInspectionSection /> : null}
        {tab === "maintenance" ? <ProcessingMaintenanceSection /> : null}
      </WorkspacePanel>
    </WorkspacePage>
  );
}
