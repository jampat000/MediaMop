import { useState } from "react";
import {
  mmModuleTabBlurbBandClass,
  mmModuleTabBlurbTextClass,
} from "../../lib/ui/mm-module-tab-blurb";
import { mmSectionTabClass } from "../../lib/ui/mm-control-roles";
import { usePrunerInstancesQuery } from "../../lib/pruner/queries";
import { PRUNER_TAB_BLURBS } from "./pruner-page-constants";
import type { TopTab } from "./pruner-page-types";
import { ProviderConfigurationWorkspace } from "./pruner-provider-configuration-workspace";
import { TopLevelJobs } from "./pruner-top-level-jobs";
import { TopLevelOverview } from "./pruner-top-level-overview";

export function PrunerInstancesListPage() {
  const q = usePrunerInstancesQuery();
  const [topTab, setTopTab] = useState<TopTab>("overview");
  const instances = q.data ?? [];

  return (
    <div className="mm-page w-full min-w-0" data-testid="pruner-scope-page">
      <header className="mm-page__intro !mb-0">
        <p className="mm-page__eyebrow">MediaMop</p>
        <h1 className="mm-page__title">Pruner</h1>
        <p className="mm-page__subtitle max-w-3xl">
          Library cleanup for{" "}
          <strong className="text-[var(--mm-text)]">Emby</strong>,{" "}
          <strong className="text-[var(--mm-text)]">Jellyfin</strong>, and{" "}
          <strong className="text-[var(--mm-text)]">Plex</strong>. Each provider
          tab has Connection, Cleanup, and Schedule for that server.
        </p>
      </header>

      <nav
        className="mb-5 mt-3 flex gap-2.5 overflow-x-auto sm:mt-4 sm:flex-wrap sm:overflow-visible"
        aria-label="Pruner sections"
        data-testid="pruner-top-level-tabs"
      >
        {(
          [
            ["overview", "Overview"],
            ["emby", "Emby"],
            ["jellyfin", "Jellyfin"],
            ["plex", "Plex"],
            ["jobs", "Jobs"],
          ] as const
        ).map(([id, label]) => (
          <button
            key={id}
            type="button"
            role="tab"
            aria-selected={topTab === id || (topTab === "schedule" && id === "emby")}
            className={mmSectionTabClass(
              topTab === id || (topTab === "schedule" && id === "emby"),
            )}
            onClick={() => setTopTab(id)}
          >
            {label}
          </button>
        ))}
      </nav>

      <div
        className="mm-bubble-stack"
        role="tabpanel"
        aria-label={
          (
            {
              overview: "Overview",
              emby: "Emby",
              jellyfin: "Jellyfin",
              plex: "Plex",
              jobs: "Jobs",
              schedule: "Emby",
            } as const
          )[topTab]
        }
      >
        <div className={mmModuleTabBlurbBandClass} data-testid="pruner-tab-blurb">
          <p className={mmModuleTabBlurbTextClass}>{PRUNER_TAB_BLURBS[topTab]}</p>
        </div>
        <div className="min-w-0">
          {q.isLoading ? (
            <p className="text-sm text-[var(--mm-text2)]">
              Loading provider instances...
            </p>
          ) : null}
          {q.isError ? (
            <p className="text-sm text-red-600">{(q.error as Error).message}</p>
          ) : null}
          {!q.isLoading && !q.isError ? (
            topTab === "overview" ? (
              <TopLevelOverview
                instances={instances}
                onOpenProviderTab={(t) => setTopTab(t)}
                onNavigateTopTab={(t) => setTopTab(t)}
              />
            ) : topTab === "jobs" ? (
              <TopLevelJobs instances={instances} />
            ) : topTab === "schedule" ? (
              <ProviderConfigurationWorkspace
                provider="emby"
                allInstances={instances}
                initialSection="schedule"
              />
            ) : (
              <ProviderConfigurationWorkspace provider={topTab} allInstances={instances} />
            )
          ) : null}
        </div>
      </div>
    </div>
  );
}
