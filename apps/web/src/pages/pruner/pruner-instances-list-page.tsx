import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { fetcherSectionTabClass } from "../fetcher/fetcher-menu-button";
import type { PrunerJobsInspectionRow, PrunerServerInstance } from "../../lib/pruner/api";
import { usePrunerInstancesQuery, usePrunerJobsInspectionQuery } from "../../lib/pruner/queries";
import { PrunerConnectionTab } from "./pruner-connection-tab";
import { PrunerInstanceOverviewTab } from "./pruner-instance-overview-tab";
import { PrunerScopeTab } from "./pruner-scope-tab";

type TopTab = "overview" | "emby" | "jellyfin" | "plex" | "schedules" | "jobs";
type ProviderTab = "emby" | "jellyfin" | "plex";
type ProviderSection = "overview" | "movies" | "tv" | "connection";

function providerLabel(p: ProviderTab): string {
  if (p === "emby") return "Emby";
  if (p === "jellyfin") return "Jellyfin";
  return "Plex";
}

function parseServerInstanceId(job: PrunerJobsInspectionRow): number | null {
  if (!job.payload_json) return null;
  try {
    const parsed = JSON.parse(job.payload_json) as { server_instance_id?: unknown };
    const sid = parsed.server_instance_id;
    return typeof sid === "number" && Number.isFinite(sid) ? sid : null;
  } catch {
    return null;
  }
}

function ProviderSetupNeeded({
  provider,
  section,
}: {
  provider: ProviderTab;
  section: ProviderSection;
}) {
  const p = providerLabel(provider);
  const sectionLabel = section === "tv" ? "TV" : section === "movies" ? "Movies" : section[0].toUpperCase() + section.slice(1);
  return (
    <section
      className="rounded-md border border-dashed border-[var(--mm-border)] bg-[var(--mm-surface2)]/35 px-4 py-4 text-sm text-[var(--mm-text2)]"
      data-testid={`pruner-provider-setup-needed-${provider}-${section}`}
    >
      <h3 className="text-sm font-semibold text-[var(--mm-text1)]">
        {p} {sectionLabel} — setup needed
      </h3>
      <p className="mt-2">
        No {p} instance is registered yet, so this section has no instance-backed settings to edit. Register a {p} server
        instance first, then this tab controls that provider only.
      </p>
      <ul className="mt-2 list-inside list-disc space-y-1 text-xs sm:text-sm">
        <li>Provider settings stay separate — no cross-provider sharing.</li>
        <li>Movies/TV remain scoped inside the selected {p} instance.</li>
        <li>Preview/apply outcomes appear after jobs run.</li>
      </ul>
    </section>
  );
}

function ProviderWorkspace({
  provider,
  allInstances,
}: {
  provider: ProviderTab;
  allInstances: PrunerServerInstance[];
}) {
  const providerInstances = useMemo(
    () => allInstances.filter((x) => x.provider === provider),
    [allInstances, provider],
  );
  const [activeSection, setActiveSection] = useState<ProviderSection>("overview");
  const [selectedInstanceId, setSelectedInstanceId] = useState<number | null>(
    providerInstances.length ? providerInstances[0]!.id : null,
  );
  const selectedInstance = providerInstances.find((x) => x.id === selectedInstanceId) ?? providerInstances[0];
  const hasInstance = Boolean(selectedInstance);
  const providerName = providerLabel(provider);

  return (
    <section className="space-y-4" data-testid={`pruner-provider-tab-${provider}`}>
      <div className="rounded-md border border-[var(--mm-border)] bg-[var(--mm-card-bg)] px-4 py-3">
        <h2 className="text-base font-semibold text-[var(--mm-text1)]">{providerName} workspace</h2>
        <p className="mt-1 text-sm text-[var(--mm-text2)]">
          {providerName} configuration is isolated from Emby/Jellyfin/Plex peers. Movies and TV are secondary scopes
          under this provider only.
        </p>
        {providerInstances.length > 1 ? (
          <div className="mt-2 flex flex-wrap gap-2 text-xs">
            {providerInstances.map((inst) => (
              <button
                key={inst.id}
                type="button"
                className={fetcherSectionTabClass(inst.id === selectedInstance?.id)}
                onClick={() => setSelectedInstanceId(inst.id)}
              >
                {inst.display_name}
              </button>
            ))}
          </div>
        ) : null}
      </div>

      <nav
        className="mt-1 flex flex-wrap gap-2.5 border-b border-[var(--mm-border)] pb-3.5"
        aria-label={`${providerName} sections`}
        data-testid={`pruner-provider-sections-${provider}`}
      >
        {(["overview", "movies", "tv", "connection"] as const).map((s) => (
          <button
            key={s}
            type="button"
            className={fetcherSectionTabClass(activeSection === s)}
            onClick={() => setActiveSection(s)}
          >
            {s === "tv" ? "TV" : s[0].toUpperCase() + s.slice(1)}
          </button>
        ))}
      </nav>

      {!hasInstance ? (
        <ProviderSetupNeeded provider={provider} section={activeSection} />
      ) : activeSection === "overview" ? (
        <PrunerInstanceOverviewTab contextOverride={{ instanceId: selectedInstance.id, instance: selectedInstance }} />
      ) : activeSection === "movies" ? (
        <PrunerScopeTab
          scope="movies"
          contextOverride={{ instanceId: selectedInstance.id, instance: selectedInstance }}
        />
      ) : activeSection === "tv" ? (
        <PrunerScopeTab scope="tv" contextOverride={{ instanceId: selectedInstance.id, instance: selectedInstance }} />
      ) : (
        <PrunerConnectionTab contextOverride={{ instanceId: selectedInstance.id, instance: selectedInstance }} />
      )}

      {selectedInstance ? (
        <p className="text-xs text-[var(--mm-text2)]">
          Deep-link to classic instance route:{" "}
          <Link
            to={`/app/pruner/instances/${selectedInstance.id}/overview`}
            className="font-semibold text-[var(--mm-accent)] underline-offset-2 hover:underline"
          >
            Open {selectedInstance.display_name}
          </Link>
        </p>
      ) : null}
    </section>
  );
}

function TopLevelOverview({ instances }: { instances: PrunerServerInstance[] }) {
  return (
    <section className="space-y-4" data-testid="pruner-top-overview-tab">
      <div className="rounded-md border border-[var(--mm-border)] bg-[var(--mm-card-bg)] px-4 py-4 text-sm text-[var(--mm-text2)]">
        <h2 className="text-base font-semibold text-[var(--mm-text1)]">Overview</h2>
        <p className="mt-1">
          Pruner is a provider tool for <strong className="text-[var(--mm-text)]">Emby</strong>,{" "}
          <strong className="text-[var(--mm-text)]">Jellyfin</strong>, and{" "}
          <strong className="text-[var(--mm-text)]">Plex</strong>. Providers stay separate, instances stay separate, and
          Movies/TV are provider-scoped sub-tabs.
        </p>
        <ul className="mt-2 list-inside list-disc space-y-1 text-xs sm:text-sm">
          <li>Use provider tabs to manage Overview, Movies, TV, and Connection for one provider workspace.</li>
          <li>Use Schedules at top level for cross-provider operational cadence visibility.</li>
          <li>Use Jobs at top level for queue/worker state visibility without blurring provider ownership.</li>
        </ul>
      </div>
      {instances.length === 0 ? (
        <div
          className="rounded-md border border-dashed border-[var(--mm-border)] bg-[var(--mm-surface2)]/35 px-4 py-4 text-sm text-[var(--mm-text2)]"
          data-testid="pruner-empty-state"
        >
          <p className="font-semibold text-[var(--mm-text1)]">No Emby, Jellyfin, or Plex instances registered yet.</p>
          <p className="mt-1">
            You can still click provider tabs now to see the real structure: Overview, Movies, TV, and Connection.
            Register an instance to enable live settings and previews.
          </p>
          <p className="mt-2 text-xs">
            Nothing is shared across providers or across instance rows.
          </p>
        </div>
      ) : null}
    </section>
  );
}

function TopLevelSchedules({ instances }: { instances: PrunerServerInstance[] }) {
  return (
    <section className="space-y-3" data-testid="pruner-top-schedules-tab">
      <h2 className="text-base font-semibold text-[var(--mm-text1)]">Schedules</h2>
      <p className="text-sm text-[var(--mm-text2)]">
        Top-level operational view across providers. Each row still maps to one provider instance and one scope.
      </p>
      {instances.length === 0 ? (
        <p className="rounded-md border border-dashed border-[var(--mm-border)] bg-[var(--mm-surface2)]/35 px-4 py-3 text-sm text-[var(--mm-text2)]">
          Register provider instances first; schedule rows populate per instance and per scope.
        </p>
      ) : (
        <div className="overflow-x-auto rounded-md border border-[var(--mm-border)]">
          <table className="w-full min-w-[34rem] border-collapse text-left text-sm">
            <thead className="bg-[var(--mm-surface2)] text-xs uppercase text-[var(--mm-text2)]">
              <tr>
                <th className="px-2 py-2">Provider</th>
                <th className="px-2 py-2">Instance</th>
                <th className="px-2 py-2">Scope</th>
                <th className="px-2 py-2">Scheduled preview</th>
                <th className="px-2 py-2">Interval (s)</th>
                <th className="px-2 py-2">Last enqueue</th>
              </tr>
            </thead>
            <tbody>
              {instances.flatMap((inst) =>
                inst.scopes.map((sc) => (
                  <tr key={`${inst.id}-${sc.media_scope}`} className="border-t border-[var(--mm-border)]">
                    <td className="px-2 py-2 capitalize">{inst.provider}</td>
                    <td className="px-2 py-2">{inst.display_name}</td>
                    <td className="px-2 py-2 uppercase">{sc.media_scope}</td>
                    <td className="px-2 py-2">{sc.scheduled_preview_enabled ? "On" : "Off"}</td>
                    <td className="px-2 py-2">{sc.scheduled_preview_interval_seconds}</td>
                    <td className="px-2 py-2">{sc.last_scheduled_preview_enqueued_at ?? "—"}</td>
                  </tr>
                )),
              )}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}

function TopLevelJobs({ instances }: { instances: PrunerServerInstance[] }) {
  const jobsQ = usePrunerJobsInspectionQuery(50);
  const byId = useMemo(() => new Map(instances.map((x) => [x.id, x])), [instances]);
  return (
    <section className="space-y-3" data-testid="pruner-top-jobs-tab">
      <h2 className="text-base font-semibold text-[var(--mm-text1)]">Jobs</h2>
      <p className="text-sm text-[var(--mm-text2)]">
        Top-level queue visibility. Provider/instance linkage is derived from job payload where available.
      </p>
      {jobsQ.isLoading ? <p className="text-sm text-[var(--mm-text2)]">Loading jobs…</p> : null}
      {jobsQ.isError ? <p className="text-sm text-red-600">{(jobsQ.error as Error).message}</p> : null}
      {jobsQ.data?.jobs?.length ? (
        <div className="overflow-x-auto rounded-md border border-[var(--mm-border)]">
          <table className="w-full min-w-[42rem] border-collapse text-left text-sm">
            <thead className="bg-[var(--mm-surface2)] text-xs uppercase text-[var(--mm-text2)]">
              <tr>
                <th className="px-2 py-2">Job</th>
                <th className="px-2 py-2">Kind</th>
                <th className="px-2 py-2">Status</th>
                <th className="px-2 py-2">Provider / instance</th>
                <th className="px-2 py-2">Updated</th>
              </tr>
            </thead>
            <tbody>
              {jobsQ.data.jobs.map((job) => {
                const sid = parseServerInstanceId(job);
                const inst = sid ? byId.get(sid) : undefined;
                return (
                  <tr key={job.id} className="border-t border-[var(--mm-border)]">
                    <td className="px-2 py-2 font-mono text-xs">#{job.id}</td>
                    <td className="px-2 py-2 text-xs">{job.job_kind}</td>
                    <td className="px-2 py-2">{job.status}</td>
                    <td className="px-2 py-2 text-xs">
                      {inst ? `${inst.provider} / ${inst.display_name}` : sid ? `instance #${sid}` : "n/a"}
                    </td>
                    <td className="px-2 py-2 text-xs">{job.updated_at}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      ) : jobsQ.data ? (
        <p className="rounded-md border border-[var(--mm-border)] bg-[var(--mm-card-bg)] px-4 py-3 text-sm text-[var(--mm-text2)]">
          No recent Pruner jobs.
        </p>
      ) : null}
      <p className="text-xs text-[var(--mm-text2)]">
        Apply removed/skipped/failed details are still tracked in{" "}
        <Link to="/app/activity" className="font-semibold text-[var(--mm-accent)] underline-offset-2 hover:underline">
          Activity
        </Link>
        .
      </p>
    </section>
  );
}

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
          Provider-first cleanup workspace for <strong className="text-[var(--mm-text)]">Emby</strong>,{" "}
          <strong className="text-[var(--mm-text)]">Jellyfin</strong>, and{" "}
          <strong className="text-[var(--mm-text)]">Plex</strong>. Configuration ownership remains instance-first.
        </p>
      </header>

      <nav
        className="mt-3 flex flex-wrap gap-2.5 border-b border-[var(--mm-border)] pb-3.5 sm:mt-4"
        aria-label="Pruner sections"
        data-testid="pruner-top-level-tabs"
      >
        {([
          ["overview", "Overview"],
          ["emby", "Emby"],
          ["jellyfin", "Jellyfin"],
          ["plex", "Plex"],
          ["schedules", "Schedules"],
          ["jobs", "Jobs"],
        ] as const).map(([id, label]) => (
          <button
            key={id}
            type="button"
            className={fetcherSectionTabClass(topTab === id)}
            onClick={() => setTopTab(id)}
          >
            {label}
          </button>
        ))}
      </nav>

      <div className="mt-6 sm:mt-7">
        {q.isLoading ? <p className="text-sm text-[var(--mm-text2)]">Loading provider instances…</p> : null}
        {q.isError ? <p className="text-sm text-red-600">{(q.error as Error).message}</p> : null}
        {!q.isLoading && !q.isError ? (
          topTab === "overview" ? (
            <TopLevelOverview instances={instances} />
          ) : topTab === "schedules" ? (
            <TopLevelSchedules instances={instances} />
          ) : topTab === "jobs" ? (
            <TopLevelJobs instances={instances} />
          ) : (
            <ProviderWorkspace provider={topTab} allInstances={instances} />
          )
        ) : null}
      </div>
    </div>
  );
}
