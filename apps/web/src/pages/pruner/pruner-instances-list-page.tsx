import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";
import { fetcherSectionTabClass } from "../fetcher/fetcher-menu-button";
import type { PrunerJobsInspectionRow, PrunerServerInstance } from "../../lib/pruner/api";
import { patchPrunerInstance, postPrunerConnectionTest, postPrunerInstance } from "../../lib/pruner/api";
import { useMeQuery } from "../../lib/auth/queries";
import { usePrunerInstancesQuery, usePrunerJobsInspectionQuery } from "../../lib/pruner/queries";
import { PrunerScopeTab } from "./pruner-scope-tab";
import { formatPrunerDateTime } from "./pruner-ui-utils";

type TopTab = "overview" | "emby" | "jellyfin" | "plex" | "schedules" | "jobs";
type ProviderTab = "emby" | "jellyfin" | "plex";

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

function activeRuleCount(scope: PrunerServerInstance["scopes"][number]): number {
  return [
    scope.missing_primary_media_reported_enabled,
    scope.never_played_stale_reported_enabled,
    scope.watched_tv_reported_enabled,
    scope.watched_movies_reported_enabled,
    scope.watched_movie_low_rating_reported_enabled,
    scope.unwatched_movie_stale_reported_enabled,
  ].filter(Boolean).length;
}

function providerCredentialLabel(provider: ProviderTab): string {
  return provider === "plex" ? "Token" : "API key";
}

function DisabledScopeSection({ scope }: { scope: "tv" | "movies" }) {
  const scopeLabel = scope === "tv" ? "TV configuration" : "Movies configuration";
  return (
    <section
      className="space-y-2 rounded-md border border-dashed border-[var(--mm-border)] bg-[var(--mm-surface2)]/35 px-4 py-3 opacity-75"
      data-testid={`pruner-provider-config-disabled-${scope}`}
    >
      <h4 className="text-sm font-semibold text-[var(--mm-text1)]">{scopeLabel}</h4>
      <p className="text-xs text-[var(--mm-text2)]">
        These controls are visible now and activate after the provider connection is saved.
      </p>
      <label className="flex items-center gap-2 text-sm text-[var(--mm-text2)]">
        <input type="checkbox" disabled />
        Enable missing primary media rule
      </label>
      <label className="flex items-center gap-2 text-sm text-[var(--mm-text2)]">
        <input type="checkbox" disabled />
        Enable watched/stale cleanup rule
      </label>
      <label className="text-xs text-[var(--mm-text2)]">
        Preview filter token list
        <input
          type="text"
          disabled
          placeholder="e.g. Drama, Jane Doe"
          className="mt-1 w-full rounded border border-[var(--mm-border)] bg-[var(--mm-surface2)] px-2 py-1 text-sm"
        />
      </label>
      <button type="button" disabled className="rounded-md border border-[var(--mm-border)] px-3 py-1 text-xs">
        Save {scope === "tv" ? "TV" : "Movies"} settings
      </button>
    </section>
  );
}

function ProviderWorkspace({ provider, allInstances }: { provider: ProviderTab; allInstances: PrunerServerInstance[] }) {
  const me = useMeQuery();
  const q = useQueryClient();
  const canOperate = me.data?.role === "admin" || me.data?.role === "operator";
  const providerName = providerLabel(provider);
  const providerInstances = useMemo(() => allInstances.filter((x) => x.provider === provider), [allInstances, provider]);
  const [selectedInstanceId, setSelectedInstanceId] = useState<number | null>(providerInstances[0]?.id ?? null);
  const selectedInstance = providerInstances.find((x) => x.id === selectedInstanceId) ?? providerInstances[0];
  const hasInstance = Boolean(selectedInstance);
  const [displayNameDraft, setDisplayNameDraft] = useState(providerName);
  const [baseUrlDraft, setBaseUrlDraft] = useState("");
  const [credentialDraft, setCredentialDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    setSelectedInstanceId(providerInstances[0]?.id ?? null);
  }, [providerInstances.length, provider]);

  useEffect(() => {
    setDisplayNameDraft(selectedInstance?.display_name ?? providerName);
    setBaseUrlDraft(selectedInstance?.base_url ?? "");
    setCredentialDraft("");
  }, [selectedInstance?.id, selectedInstance?.display_name, selectedInstance?.base_url, providerName]);

  async function saveConnection() {
    setBusy(true);
    setErr(null);
    setMsg(null);
    try {
      const trimmedName = displayNameDraft.trim() || providerName;
      const trimmedUrl = baseUrlDraft.trim();
      if (!trimmedUrl) throw new Error("Server URL is required.");
      if (!hasInstance && !credentialDraft.trim()) {
        throw new Error(`${providerCredentialLabel(provider)} is required to create a new ${providerName} connection.`);
      }
      const credentialKey = provider === "plex" ? "auth_token" : "api_key";
      const credentials = credentialDraft.trim() ? { [credentialKey]: credentialDraft.trim() } : undefined;
      if (selectedInstance) {
        await patchPrunerInstance(selectedInstance.id, {
          display_name: trimmedName,
          base_url: trimmedUrl,
          ...(credentials ? { credentials } : {}),
        });
      } else {
        await postPrunerInstance({
          provider,
          display_name: trimmedName,
          base_url: trimmedUrl,
          credentials: credentials ?? {},
        });
      }
      await q.invalidateQueries({ queryKey: ["pruner", "instances"] });
      setMsg(hasInstance ? "Connection details saved." : `${providerName} connection saved. Configuration is now active.`);
      setCredentialDraft("");
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function runConnectionTest() {
    if (!selectedInstance) return;
    setBusy(true);
    setErr(null);
    setMsg(null);
    try {
      const res = await postPrunerConnectionTest(selectedInstance.id);
      await q.invalidateQueries({ queryKey: ["pruner", "instances"] });
      setMsg(`Queued connection test job #${res.pruner_job_id}.`);
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="space-y-4" data-testid={`pruner-provider-tab-${provider}`}>
      <header className="rounded-md border border-[var(--mm-border)] bg-[var(--mm-card-bg)] px-4 py-3">
        <h2 className="text-base font-semibold text-[var(--mm-text1)]">{providerName}</h2>
        <p className="mt-1 text-sm text-[var(--mm-text2)]">
          Flat provider workspace: connection and both media scopes on one page, no nested tabs.
        </p>
      </header>
      <section className="space-y-3 rounded-md border border-[var(--mm-border)] bg-[var(--mm-card-bg)] px-4 py-4" data-testid={`pruner-provider-connection-${provider}`}>
        <h3 className="text-sm font-semibold text-[var(--mm-text)]">Connection</h3>
        <p className="text-xs text-[var(--mm-text2)]">
          {provider === "plex"
            ? "Plex requires a token. Save it here, then run connection tests and activate configuration below."
            : `${providerName} requires an API key. Save it here, then run connection tests and activate configuration below.`}
        </p>
        {providerInstances.length > 1 ? (
          <label className="text-xs text-[var(--mm-text2)]">
            Instance
            <select
              className="mt-1 w-full rounded border border-[var(--mm-border)] bg-[var(--mm-surface2)] px-2 py-1 text-sm text-[var(--mm-text)]"
              value={selectedInstance?.id ?? ""}
              onChange={(e) => setSelectedInstanceId(Number(e.target.value))}
              disabled={busy}
            >
              {providerInstances.map((inst) => (
                <option key={inst.id} value={inst.id}>
                  {inst.display_name}
                </option>
              ))}
            </select>
          </label>
        ) : null}
        <div className="grid gap-3 md:grid-cols-2">
          <label className="text-xs text-[var(--mm-text2)]">
            Display name
            <input
              type="text"
              value={displayNameDraft}
              onChange={(e) => setDisplayNameDraft(e.target.value)}
              disabled={busy || !canOperate}
              className="mt-1 w-full rounded border border-[var(--mm-border)] bg-[var(--mm-surface2)] px-2 py-1 text-sm text-[var(--mm-text)]"
            />
          </label>
          <label className="text-xs text-[var(--mm-text2)]">
            Server URL
            <input
              type="url"
              value={baseUrlDraft}
              onChange={(e) => setBaseUrlDraft(e.target.value)}
              disabled={busy || !canOperate}
              placeholder="http://server:8096"
              className="mt-1 w-full rounded border border-[var(--mm-border)] bg-[var(--mm-surface2)] px-2 py-1 text-sm text-[var(--mm-text)]"
            />
          </label>
        </div>
        <label className="block text-xs text-[var(--mm-text2)]">
          {providerCredentialLabel(provider)}
          <input
            type="password"
            value={credentialDraft}
            onChange={(e) => setCredentialDraft(e.target.value)}
            disabled={busy || !canOperate}
            placeholder={provider === "plex" ? "Plex token" : `${providerName} API key`}
            className="mt-1 w-full rounded border border-[var(--mm-border)] bg-[var(--mm-surface2)] px-2 py-1 text-sm text-[var(--mm-text)]"
          />
        </label>
        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            className="rounded-md bg-[var(--mm-accent)] px-3 py-1.5 text-sm font-medium text-white disabled:opacity-50"
            disabled={busy || !canOperate}
            onClick={() => void saveConnection()}
          >
            Save connection
          </button>
          <button
            type="button"
            className="rounded-md border border-[var(--mm-border)] px-3 py-1.5 text-sm font-medium text-[var(--mm-text)] disabled:opacity-50"
            disabled={busy || !canOperate || !selectedInstance}
            onClick={() => void runConnectionTest()}
          >
            Test connection
          </button>
        </div>
        <div className="rounded border border-[var(--mm-border)] bg-[var(--mm-surface2)]/40 px-3 py-2 text-xs text-[var(--mm-text2)]">
          <p>
            Last test:{" "}
            <strong className="text-[var(--mm-text1)]">{formatPrunerDateTime(selectedInstance?.last_connection_test_at ?? null)}</strong>
          </p>
          <p>
            Status:{" "}
            <strong className="text-[var(--mm-text1)]">
              {selectedInstance?.last_connection_test_ok == null ? "No result yet" : selectedInstance.last_connection_test_ok ? "OK" : "Failed"}
            </strong>
          </p>
          <p>Detail: {selectedInstance?.last_connection_test_detail ?? "Save connection and run a test to populate status."}</p>
        </div>
        {err ? <p className="text-sm text-red-600">{err}</p> : null}
        {msg ? <p className="text-sm text-[var(--mm-text)]">{msg}</p> : null}
      </section>
      <section className="space-y-3" data-testid={`pruner-provider-configuration-${provider}`}>
        <h3 className="text-sm font-semibold text-[var(--mm-text)]">Configuration</h3>
        {!selectedInstance ? (
          <p className="text-xs text-[var(--mm-text2)]">
            Configuration controls are shown below but inactive until this provider connection is saved.
          </p>
        ) : null}
        {provider === "plex" ? (
          <p className="text-xs text-[var(--mm-text2)]" data-testid="pruner-provider-plex-unsupported-note">
            Plex remains truthful: unsupported rules stay explicitly marked in each scope section; token wording is used throughout.
          </p>
        ) : null}
        <div className="grid gap-4 xl:grid-cols-2">
          <div>
            {selectedInstance ? (
              <PrunerScopeTab scope="tv" contextOverride={{ instanceId: selectedInstance.id, instance: selectedInstance }} />
            ) : (
              <DisabledScopeSection scope="tv" />
            )}
          </div>
          <div>
            {selectedInstance ? (
              <PrunerScopeTab scope="movies" contextOverride={{ instanceId: selectedInstance.id, instance: selectedInstance }} />
            ) : (
              <DisabledScopeSection scope="movies" />
            )}
          </div>
        </div>
      </section>
    </section>
  );
}

function TopLevelOverview({ instances }: { instances: PrunerServerInstance[] }) {
  const jobsQ = usePrunerJobsInspectionQuery(50);
  const providers: ProviderTab[] = ["emby", "jellyfin", "plex"];
  const providerCards = providers.map((provider) => {
    const rows = instances.filter((x) => x.provider === provider);
    const first = rows[0];
    const scopeRows = first?.scopes ?? [];
    const activeRules = scopeRows.reduce((acc, scope) => acc + activeRuleCount(scope), 0);
    const previews = scopeRows.filter((scope) => scope.last_preview_at);
    const latestPreview = previews.sort((a, b) =>
      String(b.last_preview_at ?? "").localeCompare(String(a.last_preview_at ?? "")),
    )[0];
    const providerJobs = jobsQ.data?.jobs?.filter((j) => {
      const sid = parseServerInstanceId(j);
      return sid != null && rows.some((row) => row.id === sid);
    });
    return { provider, rows, first, activeRules, latestPreview, latestJob: providerJobs?.[0] };
  });
  return (
    <section className="space-y-4" data-testid="pruner-top-overview-tab">
      <div className="rounded-md border border-[var(--mm-border)] bg-[var(--mm-card-bg)] px-4 py-4 text-sm text-[var(--mm-text2)]">
        <h2 className="text-base font-semibold text-[var(--mm-text1)]">Overview</h2>
        <p className="mt-1">
          Pruner is a provider tool for <strong className="text-[var(--mm-text)]">Emby</strong>,{" "}
          <strong className="text-[var(--mm-text)]">Jellyfin</strong>, and{" "}
          <strong className="text-[var(--mm-text)]">Plex</strong>. Provider tabs hold flat workspaces with connection,
          TV config, and Movies config on one page.
        </p>
        <ul className="mt-2 list-inside list-disc space-y-1 text-xs sm:text-sm">
          <li>At-a-glance cards below report live provider status only; no fake parity values.</li>
          <li>Use Schedules at top level for cross-provider operational cadence visibility.</li>
          <li>Use Jobs at top level for queue/worker state visibility without blurring provider ownership.</li>
        </ul>
      </div>
      <div className="grid gap-4 lg:grid-cols-3">
        {providerCards.map((card) => (
          <article
            key={card.provider}
            className="space-y-2 rounded-md border border-[var(--mm-border)] bg-[var(--mm-card-bg)] px-4 py-3"
            data-testid={`pruner-overview-provider-${card.provider}`}
          >
            <h3 className="text-sm font-semibold text-[var(--mm-text1)]">{providerLabel(card.provider)}</h3>
            {card.first ? (
              <>
                <p className="text-xs text-[var(--mm-text2)]">
                  Connection status:{" "}
                  <strong className="text-[var(--mm-text1)]">
                    {card.first.last_connection_test_ok == null ? "Unknown" : card.first.last_connection_test_ok ? "OK" : "Failed"}
                  </strong>
                </p>
                <p className="text-xs text-[var(--mm-text2)]">
                  Active rules: <strong className="text-[var(--mm-text1)]">{card.activeRules}</strong>
                </p>
                <p className="text-xs text-[var(--mm-text2)]">
                  Last preview:{" "}
                  <strong className="text-[var(--mm-text1)]">
                    {card.latestPreview
                      ? `${card.latestPreview.media_scope.toUpperCase()} / ${card.latestPreview.last_preview_outcome ?? "—"}`
                      : "No preview yet"}
                  </strong>
                </p>
                <p className="text-xs text-[var(--mm-text2)]">
                  Last apply/job signal:{" "}
                  <strong className="text-[var(--mm-text1)]">
                    {card.latestJob ? `${card.latestJob.job_kind} (${card.latestJob.status})` : "No jobs yet"}
                  </strong>
                </p>
              </>
            ) : (
              <p className="text-xs text-[var(--mm-text2)]">
                No {providerLabel(card.provider)} instance yet. Connection, TV, and Movies controls are ready on the provider tab.
              </p>
            )}
          </article>
        ))}
      </div>
      {instances.length === 0 ? (
        <div
          className="rounded-md border border-dashed border-[var(--mm-border)] bg-[var(--mm-surface2)]/35 px-4 py-4 text-sm text-[var(--mm-text2)]"
          data-testid="pruner-empty-state"
        >
          <p className="font-semibold text-[var(--mm-text1)]">No Emby, Jellyfin, or Plex instances registered yet.</p>
          <p className="mt-1">
            Provider pages still show live connection forms and disabled configuration sections from first load.
            Save a connection to activate TV and Movies controls.
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
        Top-level operational view across providers. Each row maps to one provider instance and one scope.
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
        Top-level queue visibility across Pruner. Provider/instance linkage is derived from job payload where available.
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
          <strong className="text-[var(--mm-text)]">Plex</strong>. Flat provider pages keep connection, TV, and Movies on
          one tab per provider.
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
