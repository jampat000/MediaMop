import {
  MmAtGlanceCard,
  MmAtGlanceGrid,
  MmNeedsAttentionList,
  MmNextStepsButton,
  MmOverviewSection,
  MmStatCaption,
  MmStatTile,
  MmStatTileRow,
} from "../../components/overview/mm-overview-cards";
import { useEffect, useMemo, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";
import { MmOnOffSwitch } from "../../components/ui/mm-on-off-switch";
import {
  MM_SCHEDULE_TIME_WINDOW_HEADING,
  MM_SCHEDULE_TIME_WINDOW_HELPER,
  MmScheduleDayChips,
  MmScheduleTimeFields,
} from "../../components/ui/mm-schedule-window-controls";
import { mmActionButtonClass } from "../../lib/ui/mm-control-roles";
import { fetcherMenuButtonClass, fetcherSectionTabClass } from "../fetcher/fetcher-menu-button";
import { fetchCsrfToken } from "../../lib/api/auth-api";
import type { PrunerJobsInspectionRow, PrunerServerInstance } from "../../lib/pruner/api";
import { patchPrunerInstance, patchPrunerScope, postPrunerConnectionTest, postPrunerInstance } from "../../lib/pruner/api";
import { useMeQuery } from "../../lib/auth/queries";
import { usePrunerInstancesQuery, usePrunerJobsInspectionQuery, usePrunerOverviewStatsQuery } from "../../lib/pruner/queries";
import {
  PrunerDryRunControls,
  PrunerProviderRulesCard,
  type PrunerProviderRulesCardHandle,
} from "./pruner-provider-operator-workspace";
import { formatPrunerDateTime, prunerJobKindOperatorLabel } from "./pruner-ui-utils";
type TopTab = "overview" | "emby" | "jellyfin" | "plex" | "jobs" | "schedule";
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

/** Placeholder when a key is stored server-side (empty field = unchanged). */
const API_KEY_SAVED_PLACEHOLDER = "\u2022".repeat(10);

function prunerConnectionDirty(
  hasInstance: boolean,
  savedUrl: string,
  urlDraft: string,
  credentialDraft: string,
): boolean {
  const u = urlDraft.trim();
  const saved = (savedUrl ?? "").trim();
  if (hasInstance) {
    return u !== saved || credentialDraft.trim() !== "";
  }
  return u !== "" && credentialDraft.trim() !== "";
}

function defaultScope(scope: "tv" | "movies") {
  return {
    media_scope: scope,
    missing_primary_media_reported_enabled: true,
    never_played_stale_reported_enabled: false,
    never_played_min_age_days: 90,
    watched_tv_reported_enabled: scope === "tv",
    watched_movies_reported_enabled: scope === "movies",
    watched_movie_low_rating_reported_enabled: false,
    watched_movie_low_rating_max_jellyfin_emby_community_rating: 4,
    watched_movie_low_rating_max_plex_audience_rating: 4,
    unwatched_movie_stale_reported_enabled: false,
    unwatched_movie_stale_min_age_days: 90,
    preview_max_items: 500,
    preview_include_genres: [],
    preview_include_people: [],
    preview_include_people_roles: [],
    preview_year_min: null,
    preview_year_max: null,
    preview_include_studios: [],
    preview_include_collections: [],
    scheduled_preview_enabled: false,
    scheduled_preview_interval_seconds: 3600,
    scheduled_preview_hours_limited: false,
    scheduled_preview_days: "",
    scheduled_preview_start: "00:00",
    scheduled_preview_end: "23:59",
    last_scheduled_preview_enqueued_at: null,
    last_preview_run_uuid: null,
    last_preview_at: null,
    last_preview_candidate_count: null,
    last_preview_outcome: null,
    last_preview_error: null,
  };
}

function providerDisabledInstance(provider: ProviderTab): PrunerServerInstance {
  return {
    id: 0,
    provider,
    display_name: `${providerLabel(provider)} (not yet connected)`,
    base_url: "",
    enabled: false,
    last_connection_test_at: null,
    last_connection_test_ok: null,
    last_connection_test_detail: null,
    scopes: [defaultScope("tv"), defaultScope("movies")],
  };
}

function prunerConnectionPlaceholderUrl(provider: ProviderTab): string {
  if (provider === "plex") return "http://localhost:32400";
  return "http://localhost:8096";
}

function PrunerConnectionCredentialPanel({
  provider,
  allInstances,
  instanceSelection,
}: {
  provider: ProviderTab;
  allInstances: PrunerServerInstance[];
  /** When set, instance row is chosen by the parent (e.g. provider workspace) so Connection matches Cleanup. */
  instanceSelection?: {
    selectedId: number | null;
    onSelectedIdChange: (id: number | null) => void;
  };
}) {
  const me = useMeQuery();
  const q = useQueryClient();
  const canOperate = me.data?.role === "admin" || me.data?.role === "operator";
  const providerName = providerLabel(provider);
  const providerInstances = useMemo(() => allInstances.filter((x) => x.provider === provider), [allInstances, provider]);
  const [internalSelectedInstanceId, setInternalSelectedInstanceId] = useState<number | null>(providerInstances[0]?.id ?? null);
  const controlled = Boolean(instanceSelection);
  const selectedInstanceId = controlled ? instanceSelection!.selectedId : internalSelectedInstanceId;
  const setSelectedInstanceId = controlled ? instanceSelection!.onSelectedIdChange : setInternalSelectedInstanceId;
  const selectedInstance = providerInstances.find((x) => x.id === selectedInstanceId) ?? providerInstances[0];
  const hasInstance = Boolean(selectedInstance);
  const [baseUrlDraft, setBaseUrlDraft] = useState("");
  const [credentialDraft, setCredentialDraft] = useState("");
  const [showCredential, setShowCredential] = useState(false);
  const [savePending, setSavePending] = useState(false);
  const [testPending, setTestPending] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [saveJustSucceeded, setSaveJustSucceeded] = useState(false);
  const [testJustSucceeded, setTestJustSucceeded] = useState(false);

  const savedUrl = selectedInstance?.base_url ?? "";
  const dirty = prunerConnectionDirty(hasInstance, savedUrl, baseUrlDraft, credentialDraft);
  const panelBusy = savePending || testPending;
  const credentialPlaceholder =
    hasInstance && credentialDraft === ""
      ? API_KEY_SAVED_PLACEHOLDER
      : provider === "plex"
        ? "Enter token"
        : "Enter API key";

  const connectionStatusMain = !selectedInstance
    ? "Not connected yet"
    : selectedInstance.last_connection_test_ok === true
      ? "Connected"
      : selectedInstance.last_connection_test_ok === false
        ? "Last test failed"
        : "Not tested yet";

  useEffect(() => {
    if (controlled) return;
    setInternalSelectedInstanceId(providerInstances[0]?.id ?? null);
  }, [controlled, providerInstances.length, provider]);

  useEffect(() => {
    setBaseUrlDraft(selectedInstance?.base_url ?? "");
    setCredentialDraft("");
    setShowCredential(false);
  }, [selectedInstance?.id, selectedInstance?.base_url]);

  useEffect(() => {
    if (!saveJustSucceeded) {
      return;
    }
    const t = window.setTimeout(() => setSaveJustSucceeded(false), 2400);
    return () => clearTimeout(t);
  }, [saveJustSucceeded]);

  useEffect(() => {
    if (!testJustSucceeded) {
      return;
    }
    const t = window.setTimeout(() => setTestJustSucceeded(false), 2400);
    return () => clearTimeout(t);
  }, [testJustSucceeded]);

  async function saveConnection() {
    setSavePending(true);
    setErr(null);
    setSaveJustSucceeded(false);
    setTestJustSucceeded(false);
    try {
      const trimmedUrl = baseUrlDraft.trim();
      if (!trimmedUrl) throw new Error("Base URL is required.");
      if (!hasInstance && !credentialDraft.trim()) {
        throw new Error(`${providerCredentialLabel(provider)} is required to create a new ${providerName} connection.`);
      }
      const credentialKey = provider === "plex" ? "auth_token" : "api_key";
      const credentials = credentialDraft.trim() ? { [credentialKey]: credentialDraft.trim() } : undefined;
      if (selectedInstance) {
        await patchPrunerInstance(selectedInstance.id, {
          base_url: trimmedUrl,
          ...(credentials ? { credentials } : {}),
        });
      } else {
        await postPrunerInstance({
          provider,
          display_name: providerName,
          base_url: trimmedUrl,
          credentials: credentials ?? {},
        });
      }
      await q.invalidateQueries({ queryKey: ["pruner", "instances"] });
      setCredentialDraft("");
      setShowCredential(false);
      setSaveJustSucceeded(true);
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setSavePending(false);
    }
  }

  async function runConnectionTest() {
    if (!selectedInstance) return;
    setTestPending(true);
    setErr(null);
    setSaveJustSucceeded(false);
    setTestJustSucceeded(false);
    try {
      await postPrunerConnectionTest(selectedInstance.id);
      await q.invalidateQueries({ queryKey: ["pruner", "instances"] });
      setTestJustSucceeded(true);
      setShowCredential(false);
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setTestPending(false);
    }
  }

  const saveLabel = `Save ${providerName}`;
  const testLabel = `Test ${providerName}`;

  return (
    <section
      className={[
        "mm-card mm-dash-card flex h-full min-h-0 min-w-0 flex-col gap-6 transition-shadow duration-200",
        saveJustSucceeded
          ? "ring-2 ring-[var(--mm-accent-ring)] ring-offset-2 ring-offset-[var(--mm-bg-main)] shadow-[0_0_0_1px_rgba(212,175,55,0.12)]"
          : "",
      ].join(" ")}
      data-testid={`pruner-connection-panel-${provider}`}
    >
      {!controlled && providerInstances.length > 1 ? (
        <label className="block text-sm text-[var(--mm-text2)]">
          <span className="mb-1 block text-xs text-[var(--mm-text3)]">Server</span>
          <select
            className="mm-input mt-1 w-full"
            value={selectedInstance?.id ?? ""}
            onChange={(e) => setSelectedInstanceId(Number(e.target.value))}
            disabled={panelBusy || !canOperate}
          >
            {providerInstances.map((inst) => (
              <option key={inst.id} value={inst.id}>
                {inst.display_name}
              </option>
            ))}
          </select>
        </label>
      ) : null}
      <label className="block text-sm text-[var(--mm-text2)]">
        <span className="mb-1 block text-xs text-[var(--mm-text3)]">Base URL</span>
        <input
          type="url"
          autoComplete="off"
          value={baseUrlDraft}
          onChange={(e) => setBaseUrlDraft(e.target.value)}
          disabled={panelBusy || !canOperate}
          placeholder={prunerConnectionPlaceholderUrl(provider)}
          className="mm-input w-full"
        />
      </label>

      <div className="space-y-1">
        <label className="block text-sm text-[var(--mm-text2)]" htmlFor={`pruner-conn-key-${provider}`}>
          <span className="mb-1 block text-xs text-[var(--mm-text3)]">{providerCredentialLabel(provider)}</span>
        </label>
        <div className="flex flex-wrap gap-2">
          <input
            id={`pruner-conn-key-${provider}`}
            type={showCredential ? "text" : "password"}
            autoComplete="new-password"
            placeholder={credentialPlaceholder}
            className="mm-input min-w-[12rem] flex-1 text-sm tracking-normal text-[var(--mm-text)]"
            disabled={panelBusy || !canOperate}
            value={credentialDraft}
            aria-describedby={hasInstance ? `pruner-conn-key-hint-${provider}` : undefined}
            onChange={(e) => {
              const next = e.target.value;
              setCredentialDraft(next);
              if (next.trim() === "") {
                setShowCredential(false);
              }
            }}
          />
          <button
            type="button"
            className={fetcherMenuButtonClass({
              variant: "tertiary",
              disabled: !canOperate || panelBusy,
            })}
            disabled={!canOperate || panelBusy}
            onClick={() => setShowCredential((v) => !v)}
          >
            {showCredential ? "Hide" : "Show"}
          </button>
        </div>
        {hasInstance ? (
          <p id={`pruner-conn-key-hint-${provider}`} className="text-xs text-[var(--mm-text3)]">
            Leave blank to keep your saved {provider === "plex" ? "token" : "key"}, or type a new one to replace it.
          </p>
        ) : null}
      </div>

      {saveJustSucceeded ? (
        <p
          className="rounded-md border border-[rgba(212,175,55,0.45)] bg-[var(--mm-accent-soft)] px-3 py-2 text-sm font-medium text-[var(--mm-text1)]"
          role="status"
          data-testid={`pruner-connection-save-ok-${provider}`}
        >
          Saved.
        </p>
      ) : null}

      {testJustSucceeded ? (
        <p
          className="rounded-md border border-[rgba(212,175,55,0.45)] bg-[var(--mm-accent-soft)] px-3 py-2 text-sm font-medium text-[var(--mm-text1)]"
          role="status"
          data-testid={`pruner-connection-test-ok-${provider}`}
        >
          Test started — results appear here when it finishes.
        </p>
      ) : null}

      <div className="flex flex-wrap items-center gap-3">
        <button
          type="button"
          className={fetcherMenuButtonClass({
            variant: "primary",
            disabled: !canOperate || !dirty || panelBusy,
          })}
          disabled={!canOperate || !dirty || panelBusy}
          onClick={() => void saveConnection()}
        >
          {savePending ? "Saving…" : saveLabel}
        </button>
        <button
          type="button"
          className={fetcherMenuButtonClass({
            variant: "secondary",
            disabled: !canOperate || panelBusy || !selectedInstance,
          })}
          disabled={!canOperate || panelBusy || !selectedInstance}
          onClick={() => void runConnectionTest()}
        >
          {testPending ? "Testing…" : testLabel}
        </button>
      </div>

      <div
        className="mt-auto rounded-md border border-[var(--mm-border)] bg-[var(--mm-card-bg)] p-3.5 text-sm text-[var(--mm-text2)]"
        data-testid={`pruner-connection-status-${provider}`}
      >
        <p className="text-sm font-medium text-[var(--mm-text1)]">{connectionStatusMain}</p>
        <p className="mt-1 text-xs text-[var(--mm-text3)]">
          Last completed check: {formatPrunerDateTime(selectedInstance?.last_connection_test_at ?? null)}
        </p>
        {selectedInstance?.last_connection_test_detail && selectedInstance.last_connection_test_ok !== true ? (
          <p className="mt-1 text-xs text-[var(--mm-text3)]">{selectedInstance.last_connection_test_detail}</p>
        ) : null}
        {err ? (
          <p className="mt-2 text-sm text-red-400" role="alert">
            {err}
          </p>
        ) : null}
        <p className="mt-2 text-xs text-[var(--mm-text3)]">
          Each test adds a line to{" "}
          <Link to="/app/activity" className="text-[var(--mm-accent)] underline-offset-2 hover:underline">
            Activity
          </Link>{" "}
          for your records.
        </p>
      </div>
    </section>
  );
}

type ProviderWorkspaceSection = "connection" | "cleanup" | "schedule";

function ProviderConfigurationWorkspace({
  provider,
  allInstances,
  initialSection = "connection",
}: {
  provider: ProviderTab;
  allInstances: PrunerServerInstance[];
  initialSection?: ProviderWorkspaceSection;
}) {
  const providerName = providerLabel(provider);
  const providerInstances = useMemo(() => allInstances.filter((x) => x.provider === provider), [allInstances, provider]);
  const [selectedInstanceId, setSelectedInstanceId] = useState<number | null>(providerInstances[0]?.id ?? null);
  const [providerSection, setProviderSection] = useState<ProviderWorkspaceSection>(initialSection);
  const selectedInstance = providerInstances.find((x) => x.id === selectedInstanceId) ?? providerInstances[0];
  const rulesCardRef = useRef<PrunerProviderRulesCardHandle>(null);

  useEffect(() => {
    setSelectedInstanceId((prev) => {
      if (prev != null && providerInstances.some((x) => x.id === prev)) return prev;
      return providerInstances[0]?.id ?? null;
    });
  }, [provider, providerInstances]);

  useEffect(() => {
    setProviderSection(initialSection);
  }, [provider, initialSection]);

  const disabledCtx = { instanceId: 0, instance: providerDisabledInstance(provider) } as const;
  const instanceSelection = {
    selectedId: selectedInstanceId,
    onSelectedIdChange: setSelectedInstanceId,
  };

  return (
    <section className="space-y-5" data-testid={`pruner-provider-tab-${provider}`}>
      {providerInstances.length > 1 ? (
        <label className="block max-w-md text-sm text-[var(--mm-text2)]">
          <span className="mb-1 block text-xs text-[var(--mm-text3)]">Server</span>
          <select
            className="mm-input mt-1 w-full"
            value={selectedInstance?.id ?? ""}
            onChange={(e) => setSelectedInstanceId(Number(e.target.value))}
          >
            {providerInstances.map((inst) => (
              <option key={inst.id} value={inst.id}>
                {inst.display_name}
              </option>
            ))}
          </select>
        </label>
      ) : null}

      <nav
        className="flex flex-wrap gap-2 border-b border-[var(--mm-border)] pb-3"
        aria-label={`${providerName} configuration sections`}
        data-testid={`pruner-provider-subnav-${provider}`}
      >
        {(
          [
            ["connection", "Connection"],
            ["cleanup", "Cleanup"],
            ["schedule", "Schedule"],
          ] as const
        ).map(([id, label]) => (
          <button
            key={id}
            type="button"
            className={fetcherSectionTabClass(providerSection === id)}
            aria-current={providerSection === id ? "page" : undefined}
            onClick={() => setProviderSection(id)}
          >
            {label}
          </button>
        ))}
      </nav>

      <div data-testid={`pruner-provider-sections-${provider}`}>
        {providerSection === "connection" ? (
          <PrunerConnectionCredentialPanel provider={provider} allInstances={allInstances} instanceSelection={instanceSelection} />
        ) : null}

        {providerSection === "cleanup" || providerSection === "schedule" ? (
          <div
            className={providerSection !== "cleanup" ? "hidden" : undefined}
            data-testid={providerSection === "cleanup" ? "pruner-provider-cleanup-wrap" : undefined}
            aria-hidden={providerSection !== "cleanup"}
          >
            <PrunerProviderRulesCard
              ref={rulesCardRef}
              provider={provider}
              instanceId={selectedInstance?.id ?? 0}
              instance={selectedInstance ?? disabledCtx.instance}
            />
          </div>
        ) : null}

        {providerSection === "schedule" ? (
          <div className="grid gap-4 md:grid-cols-2" data-testid="pruner-provider-schedule-wrap">
            <PrunerGlobalScheduleRow
              provider={provider}
              scope="tv"
              instance={selectedInstance}
              ensureScopeSaved={async () => {
                await rulesCardRef.current?.ensureTvSaved();
              }}
            />
            <PrunerGlobalScheduleRow
              provider={provider}
              scope="movies"
              instance={selectedInstance}
              ensureScopeSaved={async () => {
                await rulesCardRef.current?.ensureMoviesSaved();
              }}
            />
          </div>
        ) : null}
      </div>
    </section>
  );
}

function scanOutcomeReadable(o: string | null | undefined): string {
  if (!o) return "—";
  const u = o.toLowerCase();
  if (u === "success") return "Finished OK";
  if (u === "failed") return "Failed";
  if (u === "unsupported") return "Not available";
  return o;
}

function buildPrunerNeedsAttention(instances: PrunerServerInstance[]): { text: string; tab: ProviderTab }[] {
  const items: { text: string; tab: ProviderTab }[] = [];
  if (instances.length === 0) {
    items.push({
      text: "No Emby, Jellyfin, or Plex servers connected — add one under Emby, Jellyfin, or Plex.",
      tab: "emby",
    });
    return items;
  }
  for (const inst of instances) {
    if (inst.last_connection_test_ok === false) {
      const label = providerLabel(inst.provider as ProviderTab);
      items.push({
        text: `${label} (${inst.display_name}) connection test failed — check Connection tab.`,
        tab: inst.provider as ProviderTab,
      });
    }
  }
  const allRulesZero = instances.every((inst) => inst.scopes.every((sc) => activeRuleCount(sc) === 0));
  if (allRulesZero) {
    items.push({
      text: "No cleanup rules are enabled — turn on rules in the Cleanup tab.",
      tab: "emby",
    });
  }
  return items.slice(0, 8);
}

const PRUNER_ATTENTION_TAB_ORDER: ProviderTab[] = ["emby", "jellyfin", "plex"];

function prunerAttentionOpenLabel(tab: ProviderTab): string {
  return `Open ${providerLabel(tab)}`;
}

function PrunerLast30StatsTiles({
  itemsRemoved,
  previewRuns,
  failedApplies,
}: {
  itemsRemoved: number;
  previewRuns: number;
  failedApplies: number;
}) {
  return (
    <div>
      <MmStatTileRow>
        <MmStatTile label="Removed" value={itemsRemoved} />
        <MmStatTile label="Preview" value={previewRuns} />
        <MmStatTile label="Failed" value={failedApplies} />
      </MmStatTileRow>
      <MmStatCaption>Library cleanup activity · last 30 days</MmStatCaption>
    </div>
  );
}

const PRUNER_NEXT_STEPS_BODY =
  "Use Emby, Jellyfin, or Plex to connect your media server and configure cleanup rules. Check Jobs for recent activity and Schedule to set up timed runs.";

function PrunerOverviewNextSteps({ onNavigate }: { onNavigate: (tab: TopTab) => void }) {
  return (
    <MmOverviewSection
      headingId="pruner-overview-next-steps-heading"
      heading="Next steps"
      data-testid="pruner-overview-next-steps"
      data-overview-order="3"
    >
      <div className="space-y-5">
        <p className="leading-relaxed">{PRUNER_NEXT_STEPS_BODY}</p>
        <div className="flex flex-wrap gap-2.5 border-t border-[var(--mm-border)] pt-4">
          <MmNextStepsButton label="Emby" onClick={() => onNavigate("emby")} />
          <MmNextStepsButton label="Jellyfin" onClick={() => onNavigate("jellyfin")} />
          <MmNextStepsButton label="Plex" onClick={() => onNavigate("plex")} />
          <MmNextStepsButton label="Jobs" onClick={() => onNavigate("jobs")} />
          <MmNextStepsButton label="Schedule" onClick={() => onNavigate("schedule")} />
        </div>
      </div>
    </MmOverviewSection>
  );
}

function PrunerOverviewNeedsAttention({
  items,
  onOpenProviderTab,
}: {
  items: { text: string; tab: ProviderTab }[];
  onOpenProviderTab: (tab: ProviderTab) => void;
}) {
  const actionTabs = PRUNER_ATTENTION_TAB_ORDER.filter((t) => items.some((row) => row.tab === t));
  return (
    <MmOverviewSection
      headingId="pruner-overview-needs-attention-heading"
      heading="Needs attention"
      data-testid="pruner-overview-needs-attention"
      data-overview-order="2"
    >
      <MmNeedsAttentionList
        items={items.map((row) => row.text)}
        actions={
          actionTabs.length > 0 ? (
            <>
              {actionTabs.map((tab) => (
                <MmNextStepsButton key={tab} label={prunerAttentionOpenLabel(tab)} onClick={() => onOpenProviderTab(tab)} />
              ))}
            </>
          ) : undefined
        }
      />
    </MmOverviewSection>
  );
}

function TopLevelOverview({
  instances,
  onOpenProviderTab,
  onNavigateTopTab,
}: {
  instances: PrunerServerInstance[];
  onOpenProviderTab: (tab: ProviderTab) => void;
  onNavigateTopTab: (tab: TopTab) => void;
}) {
  const jobsQ = usePrunerJobsInspectionQuery(50);
  const statsQ = usePrunerOverviewStatsQuery();
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
    const latestApplyLike = providerJobs?.find((j) => String(j.job_kind).toLowerCase().includes("apply")) ?? providerJobs?.[0];
    return { provider, rows, first, activeRules, latestPreview, latestJob: latestApplyLike };
  });

  const attentionItems = buildPrunerNeedsAttention(instances);

  const last30Body = statsQ.isPending ? (
    <p className="text-[var(--mm-text3)]">Loading…</p>
  ) : statsQ.isError ? (
    <p className="text-red-400">{(statsQ.error as Error).message}</p>
  ) : statsQ.data ? (
    <PrunerLast30StatsTiles
      itemsRemoved={statsQ.data.items_removed}
      previewRuns={statsQ.data.preview_runs}
      failedApplies={statsQ.data.failed_applies}
    />
  ) : (
    <p className="text-[var(--mm-text3)]">—</p>
  );

  return (
    <section className="space-y-6" data-testid="pruner-top-overview-tab">
      <MmOverviewSection
        headingId="pruner-overview-at-a-glance-heading"
        heading="At a glance"
        data-testid="pruner-overview-at-a-glance"
        data-overview-order="1"
      >
        <MmAtGlanceGrid className="grid grid-cols-1 gap-4 sm:grid-cols-2 sm:gap-x-5 sm:gap-y-5 lg:grid-cols-12 lg:gap-x-5 lg:gap-y-6">
          <MmAtGlanceCard
            glanceOrder="1"
            title="Last 30 days"
            emphasis
            body={last30Body}
            gridClassName="lg:col-span-4"
          />
          {providerCards.map((card, i) => {
            const order = String(i + 2) as "2" | "3" | "4";
            const providerGridClass =
              i === 2 ? "sm:col-span-2 lg:col-span-12" : "lg:col-span-4";
            const body = card.first ? (
              <div className="space-y-1.5">
                <p>
                  <span className="text-[var(--mm-text3)]">Connection test:</span>{" "}
                  <span className="font-medium text-[var(--mm-text1)]">
                    {card.first.last_connection_test_ok == null ? "Not run yet" : card.first.last_connection_test_ok ? "OK" : "Failed"}
                  </span>
                </p>
                <p>
                  <span className="text-[var(--mm-text3)]">Cleanup rules on:</span>{" "}
                  <span className="font-medium text-[var(--mm-text1)]">{card.activeRules}</span>
                </p>
                <p>
                  <span className="text-[var(--mm-text3)]">Last library scan:</span>{" "}
                  <span className="font-medium text-[var(--mm-text1)]">
                    {card.latestPreview
                      ? `${card.latestPreview.media_scope === "tv" ? "TV" : "Movies"} · ${scanOutcomeReadable(card.latestPreview.last_preview_outcome)}`
                      : "—"}
                  </span>
                </p>
                <p>
                  <span className="text-[var(--mm-text3)]">Recent task:</span>{" "}
                  <span className="font-medium text-[var(--mm-text1)]">
                    {card.latestJob
                      ? `${prunerJobKindOperatorLabel(card.latestJob.job_kind)} (${card.latestJob.status})`
                      : "—"}
                  </span>
                </p>
              </div>
            ) : (
              <p className="text-[var(--mm-text2)]">No server saved yet. Add the address and key on that provider’s Connection tab.</p>
            );
            return (
              <MmAtGlanceCard
                key={card.provider}
                glanceOrder={order}
                title={providerLabel(card.provider)}
                body={body}
                gridClassName={providerGridClass}
                footer={
                  card.provider === "emby" ? (
                    <MmNextStepsButton label="Open Emby" onClick={() => onNavigateTopTab("emby")} />
                  ) : card.provider === "jellyfin" ? (
                    <MmNextStepsButton label="Open Jellyfin" onClick={() => onNavigateTopTab("jellyfin")} />
                  ) : (
                    <MmNextStepsButton label="Open Plex" onClick={() => onNavigateTopTab("plex")} />
                  )
                }
              />
            );
          })}
        </MmAtGlanceGrid>
      </MmOverviewSection>

      <PrunerOverviewNeedsAttention items={attentionItems} onOpenProviderTab={onOpenProviderTab} />

      <PrunerOverviewNextSteps onNavigate={onNavigateTopTab} />
    </section>
  );
}

function PrunerGlobalScheduleRow({
  provider,
  scope,
  instance,
  ensureScopeSaved,
}: {
  provider: ProviderTab;
  scope: "tv" | "movies";
  instance: PrunerServerInstance | undefined;
  ensureScopeSaved: () => Promise<void>;
}) {
  const qc = useQueryClient();
  const me = useMeQuery();
  const canOperate = me.data?.role === "admin" || me.data?.role === "operator";
  const scopeRow = instance?.scopes.find((s) => s.media_scope === scope);
  const [schedHoursLimited, setSchedHoursLimited] = useState(false);
  const [schedDays, setSchedDays] = useState("");
  const [schedStart, setSchedStart] = useState("00:00");
  const [schedEnd, setSchedEnd] = useState("23:59");
  const [previewCap, setPreviewCap] = useState(500);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [dryRunEnabled, setDryRunEnabled] = useState(true);

  useEffect(() => {
    if (!scopeRow) {
      setSchedHoursLimited(false);
      setSchedDays("");
      setSchedStart("00:00");
      setSchedEnd("23:59");
      setPreviewCap(500);
      return;
    }
    setSchedHoursLimited(scopeRow.scheduled_preview_hours_limited ?? false);
    setSchedDays(scopeRow.scheduled_preview_days ?? "");
    setSchedStart(scopeRow.scheduled_preview_start ?? "00:00");
    setSchedEnd(scopeRow.scheduled_preview_end ?? "23:59");
    setPreviewCap(scopeRow.preview_max_items);
  }, [
    scopeRow?.scheduled_preview_hours_limited,
    scopeRow?.scheduled_preview_days,
    scopeRow?.scheduled_preview_start,
    scopeRow?.scheduled_preview_end,
    scopeRow?.preview_max_items,
    instance?.id,
  ]);

  const scheduleFieldsDirty =
    scopeRow != null &&
    (schedHoursLimited !== (scopeRow.scheduled_preview_hours_limited ?? false) ||
      schedDays !== (scopeRow.scheduled_preview_days ?? "") ||
      schedStart !== (scopeRow.scheduled_preview_start ?? "00:00") ||
      schedEnd !== (scopeRow.scheduled_preview_end ?? "23:59") ||
      previewCap !== scopeRow.preview_max_items);

  async function saveRow() {
    if (!instance || !scopeRow) return;
    setMsg(null);
    setErr(null);
    setBusy(true);
    try {
      const csrf_token = await fetchCsrfToken();
      const cap = Math.max(1, Math.min(5000, Number(previewCap) || 500));
      await patchPrunerScope(instance.id, scope, {
        scheduled_preview_enabled: scopeRow.scheduled_preview_enabled,
        scheduled_preview_interval_seconds: scopeRow.scheduled_preview_interval_seconds,
        scheduled_preview_hours_limited: schedHoursLimited,
        scheduled_preview_days: schedDays,
        scheduled_preview_start: schedStart,
        scheduled_preview_end: schedEnd,
        preview_max_items: cap,
        csrf_token,
      });
      await qc.invalidateQueries({ queryKey: ["pruner", "instances"] });
      setMsg("Saved.");
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  const missing = !instance;
  const controlsDisabled = !canOperate || busy || missing;
  const saveDisabled = busy || !canOperate || missing || !scopeRow || !scheduleFieldsDirty;
  const testId = `pruner-schedule-row-${provider}-${scope}`;
  const idPrefix = `pruner-sched-${provider}-${scope}`;

  const saveScheduleLabel = scope === "tv" ? "Save TV schedule" : "Save Movies schedule";

  return (
    <section className="rounded-md border border-[var(--mm-border)] bg-[var(--mm-card-bg)] p-6" data-testid={testId}>
      <div className="space-y-6">
        <div className="space-y-3">
          <div>
            <span className="text-sm font-medium text-[var(--mm-text1)]">{MM_SCHEDULE_TIME_WINDOW_HEADING}</span>
            <p className="mt-1 text-xs leading-relaxed text-[var(--mm-text3)]">{MM_SCHEDULE_TIME_WINDOW_HELPER}</p>
          </div>
          <div className="space-y-4">
            <MmOnOffSwitch
              id={`${idPrefix}-hours-limited`}
              label="Limit to these hours"
              enabled={schedHoursLimited}
              disabled={controlsDisabled}
              onChange={setSchedHoursLimited}
            />
            <div className="space-y-2">
              <span className="text-sm font-medium text-[var(--mm-text1)]">Days</span>
              <MmScheduleDayChips scheduleDaysCsv={schedDays} disabled={controlsDisabled} onChangeCsv={setSchedDays} />
            </div>
            <MmScheduleTimeFields
              idPrefix={idPrefix}
              start={schedStart}
              end={schedEnd}
              disabled={controlsDisabled}
              onStart={setSchedStart}
              onEnd={setSchedEnd}
            />
          </div>
        </div>
        <div>
          <span className="text-sm font-medium text-[var(--mm-text1)]">Items to scan per run</span>
          <p className="mt-1 text-xs leading-relaxed text-[var(--mm-text3)]">
            How many items to check each time the scan runs. Higher numbers take longer. Maximum 5,000.
          </p>
          <input
            type="number"
            min={1}
            max={5000}
            className="mm-input mt-2 w-full max-w-xs"
            value={previewCap}
            disabled={controlsDisabled}
            onChange={(e) => setPreviewCap(Math.max(1, Math.min(5000, Number(e.target.value) || 500)))}
            aria-label="Items to scan per run"
          />
        </div>
        <p className="text-xs text-[var(--mm-text2)]">
          <span className="text-[var(--mm-text3)]">Last automatic scan:</span>{" "}
          <span className="font-medium text-[var(--mm-text1)]">
            {scopeRow?.last_scheduled_preview_enqueued_at
              ? formatPrunerDateTime(scopeRow.last_scheduled_preview_enqueued_at)
              : "Never run"}
          </span>
        </p>
        {canOperate ? (
          <button
            type="button"
            className={mmActionButtonClass({ variant: "primary", disabled: saveDisabled })}
            disabled={saveDisabled}
            onClick={() => void saveRow()}
          >
            {busy ? "Saving…" : saveScheduleLabel}
          </button>
        ) : null}
        {msg ? <p className="text-xs text-green-600">{msg}</p> : null}
        {err ? (
          <p className="text-xs text-red-500" role="alert">
            {err}
          </p>
        ) : null}

        <div className="mt-6 border-t border-[var(--mm-border)] pt-6">
          <h4 className="text-sm font-semibold text-[var(--mm-text1)]">Run now</h4>
          <p className="mt-1 text-xs leading-relaxed text-[var(--mm-text3)]">
            Run your saved cleanup criteria immediately without waiting for the schedule.
          </p>
          <div className="mt-4">
            <PrunerDryRunControls
              instanceId={instance?.id ?? 0}
              mediaScope={scope}
              testIdPrefix={`pruner-schedule-${provider}`}
              ensureSaved={ensureScopeSaved}
              dryRunEnabled={dryRunEnabled}
              onDryRunEnabledChange={setDryRunEnabled}
              runDisabled={!instance || instance.id <= 0}
              controlsDisabled={controlsDisabled}
            />
          </div>
        </div>
      </div>
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
        Recent cleanup and connection tasks. When MediaMop knows which server a task belonged to, it is shown in the
        table.
      </p>
      {jobsQ.isLoading ? <p className="text-sm text-[var(--mm-text2)]">Loading jobs…</p> : null}
      {jobsQ.isError ? <p className="text-sm text-red-600">{(jobsQ.error as Error).message}</p> : null}
      {jobsQ.data?.jobs?.length ? (
        <div className="overflow-x-auto rounded-md border border-[var(--mm-border)]">
          <table className="w-full min-w-[42rem] border-collapse text-left text-sm">
            <thead className="bg-[var(--mm-surface2)] text-xs uppercase text-[var(--mm-text2)]">
              <tr>
                <th className="px-2 py-2">Id</th>
                <th className="px-2 py-2">What ran</th>
                <th className="px-2 py-2">Status</th>
                <th className="px-2 py-2">Provider / server</th>
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
                    <td className="px-2 py-2 text-xs">{prunerJobKindOperatorLabel(job.job_kind)}</td>
                    <td className="px-2 py-2">{job.status}</td>
                    <td className="px-2 py-2 text-xs">
                      {inst ? `${inst.provider} / ${inst.display_name}` : sid ? `Server #${sid}` : "—"}
                    </td>
                    <td className="px-2 py-2 text-xs">{job.updated_at}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      ) : jobsQ.data ? (
        <p className="rounded-md border border-dashed border-[var(--mm-border)] bg-[var(--mm-surface2)]/35 px-4 py-3 text-sm text-[var(--mm-text2)]">
          No recent Pruner jobs.
        </p>
      ) : null}
      <p className="text-xs text-[var(--mm-text2)]">
        Full detail on what was deleted, skipped, or failed is in the{" "}
        <Link to="/app/activity" className="font-semibold text-[var(--mm-accent)] underline-offset-2 hover:underline">
          Activity log
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
          Library cleanup for <strong className="text-[var(--mm-text)]">Emby</strong>,{" "}
          <strong className="text-[var(--mm-text)]">Jellyfin</strong>, and{" "}
          <strong className="text-[var(--mm-text)]">Plex</strong>. Each provider tab has Connection, Cleanup, and Schedule
          for that server.
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
          ["jobs", "Jobs"],
        ] as const).map(([id, label]) => (
          <button
            key={id}
            type="button"
            role="tab"
            aria-selected={topTab === id || (topTab === "schedule" && id === "emby")}
            className={fetcherSectionTabClass(topTab === id || (topTab === "schedule" && id === "emby"))}
            onClick={() => setTopTab(id)}
          >
            {label}
          </button>
        ))}
      </nav>

      <div
        className="mt-6 sm:mt-7"
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
        {q.isLoading ? <p className="text-sm text-[var(--mm-text2)]">Loading provider instances…</p> : null}
        {q.isError ? <p className="text-sm text-red-600">{(q.error as Error).message}</p> : null}
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
            <ProviderConfigurationWorkspace provider="emby" allInstances={instances} initialSection="schedule" />
          ) : (
            <ProviderConfigurationWorkspace provider={topTab} allInstances={instances} />
          )
        ) : null}
      </div>
    </div>
  );
}
