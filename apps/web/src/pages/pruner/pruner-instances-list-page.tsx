import type { ReactNode } from "react";
import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";
import {
  FETCHER_TAB_PANEL_BLURB_CLASS,
  FETCHER_TAB_PANEL_INTRO_CLASS,
  FETCHER_TAB_PANEL_TITLE_CLASS,
} from "../fetcher/fetcher-tab-panel-intro";
import { fetcherMenuButtonClass, fetcherSectionTabClass } from "../fetcher/fetcher-menu-button";
import type { PrunerJobsInspectionRow, PrunerServerInstance } from "../../lib/pruner/api";
import { patchPrunerInstance, postPrunerConnectionTest, postPrunerInstance } from "../../lib/pruner/api";
import { useMeQuery } from "../../lib/auth/queries";
import { usePrunerInstancesQuery, usePrunerJobsInspectionQuery } from "../../lib/pruner/queries";
import { PrunerScopeTab } from "./pruner-scope-tab";
import { formatPrunerDateTime } from "./pruner-ui-utils";

type TopTab = "overview" | "connections" | "emby" | "jellyfin" | "plex" | "schedules" | "jobs";
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
    preview_year_min: null,
    preview_year_max: null,
    preview_include_studios: [],
    preview_include_collections: [],
    scheduled_preview_enabled: false,
    scheduled_preview_interval_seconds: 3600,
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

function PrunerAtGlanceCard({
  title,
  body,
  glanceOrder,
}: {
  title: string;
  body: ReactNode;
  glanceOrder: "1" | "2" | "3";
}) {
  return (
    <div
      className="flex h-full flex-col gap-3 rounded-md border border-[var(--mm-border)] bg-[var(--mm-card-bg)] p-5 text-sm"
      data-at-glance-order={glanceOrder}
    >
      <h3 className="text-sm font-semibold text-[var(--mm-text1)]">{title}</h3>
      <div className="min-h-0 flex-1 text-[var(--mm-text2)]">{body}</div>
    </div>
  );
}

function prunerConnectionPlaceholderUrl(provider: ProviderTab): string {
  if (provider === "plex") return "http://localhost:32400";
  return "http://localhost:8096";
}

function PrunerConnectionCredentialPanel({
  provider,
  allInstances,
}: {
  provider: ProviderTab;
  allInstances: PrunerServerInstance[];
}) {
  const me = useMeQuery();
  const q = useQueryClient();
  const canOperate = me.data?.role === "admin" || me.data?.role === "operator";
  const providerName = providerLabel(provider);
  const providerInstances = useMemo(() => allInstances.filter((x) => x.provider === provider), [allInstances, provider]);
  const [selectedInstanceId, setSelectedInstanceId] = useState<number | null>(providerInstances[0]?.id ?? null);
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

  const statusHeadline = !selectedInstance
    ? "Not connected yet"
    : selectedInstance.last_connection_test_ok === true
      ? "Connection status: OK"
      : selectedInstance.last_connection_test_ok === false
        ? "Connection status: Failed"
        : "Connection status: Not tested yet";

  useEffect(() => {
    setSelectedInstanceId(providerInstances[0]?.id ?? null);
  }, [providerInstances.length, provider]);

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
        "mm-card mm-dash-card flex h-full min-h-0 min-w-0 flex-col gap-7 transition-shadow duration-200",
        saveJustSucceeded
          ? "ring-2 ring-[var(--mm-accent-ring)] ring-offset-2 ring-offset-[var(--mm-bg-main)] shadow-[0_0_0_1px_rgba(212,175,55,0.12)]"
          : "",
      ].join(" ")}
      data-testid={`pruner-connection-panel-${provider}`}
    >
      <h3 className="text-base font-semibold text-[var(--mm-text1)]">{providerName}</h3>
      <p className="text-xs leading-relaxed text-[var(--mm-text2)]">
        {provider === "plex" ? "Plex server URL and token." : `${providerName} server URL and API key.`}
      </p>
      {providerInstances.length > 1 ? (
        <label className="block text-sm text-[var(--mm-text2)]">
          <span className="mb-1 block text-xs text-[var(--mm-text3)]">Instance</span>
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
          Test queued — results appear below when the job finishes.
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
        <p className="font-medium text-[var(--mm-text1)]">{statusHeadline}</p>
        <p className="mt-1 text-xs text-[var(--mm-text3)]">
          Last completed check: {formatPrunerDateTime(selectedInstance?.last_connection_test_at ?? null)}
        </p>
        {selectedInstance?.last_connection_test_detail && statusHeadline !== "Connection status: OK" ? (
          <p className="mt-1 text-xs text-[var(--mm-text3)]">{selectedInstance.last_connection_test_detail}</p>
        ) : null}
        {err ? (
          <p className="mt-2 text-sm text-red-400" role="alert">
            {err}
          </p>
        ) : null}
        <p className="mt-2 text-xs text-[var(--mm-text3)]">
          Each test also adds a line to{" "}
          <Link to="/app/activity" className="text-[var(--mm-accent)] underline-offset-2 hover:underline">
            Activity
          </Link>{" "}
          for your records.
        </p>
      </div>
    </section>
  );
}

function ConnectionsTabPanel({ allInstances }: { allInstances: PrunerServerInstance[] }) {
  const providers: ProviderTab[] = ["emby", "jellyfin", "plex"];
  return (
    <section className="mm-fetcher-module-surface mb-6" data-testid="pruner-connections-tab">
      <header className={FETCHER_TAB_PANEL_INTRO_CLASS}>
        <h2 className={FETCHER_TAB_PANEL_TITLE_CLASS}>Connections</h2>
        <p className={FETCHER_TAB_PANEL_BLURB_CLASS}>
          Credentials only. Configure cleanup rules on each provider tab (Emby, Jellyfin, Plex).
        </p>
      </header>
      <div className="mm-dash-grid gap-x-5 gap-y-6" data-testid="pruner-connection-panels-grid">
        {providers.map((p) => (
          <PrunerConnectionCredentialPanel key={p} provider={p} allInstances={allInstances} />
        ))}
      </div>
    </section>
  );
}

type ProviderWorkspaceSection = "rules" | "filters" | "schedule";

function ProviderConfigurationWorkspace({ provider, allInstances }: { provider: ProviderTab; allInstances: PrunerServerInstance[] }) {
  const providerName = providerLabel(provider);
  const providerInstances = useMemo(() => allInstances.filter((x) => x.provider === provider), [allInstances, provider]);
  const [selectedInstanceId, setSelectedInstanceId] = useState<number | null>(providerInstances[0]?.id ?? null);
  const [providerSection, setProviderSection] = useState<ProviderWorkspaceSection>("rules");
  const selectedInstance = providerInstances.find((x) => x.id === selectedInstanceId) ?? providerInstances[0];
  const hasInstance = Boolean(selectedInstance);

  useEffect(() => {
    setSelectedInstanceId(providerInstances[0]?.id ?? null);
  }, [providerInstances.length, provider]);

  useEffect(() => {
    setProviderSection("rules");
  }, [provider, selectedInstance?.id]);

  const disabledCtx = { instanceId: 0, instance: providerDisabledInstance(provider) } as const;
  const activeCtx = selectedInstance
    ? { instanceId: selectedInstance.id, instance: selectedInstance }
    : disabledCtx;

  return (
    <section className="space-y-5" data-testid={`pruner-provider-tab-${provider}`}>
      <div>
        <h2 className="text-base font-semibold text-[var(--mm-text1)]">{providerName}</h2>
        <p className="mt-1 max-w-3xl text-sm leading-snug text-[var(--mm-text2)]">
          Save credentials under <strong className="text-[var(--mm-text)]">Connections</strong>, then use Rules,
          Filters, and Schedule below.
        </p>
      </div>
      {providerInstances.length > 1 ? (
        <label className="block max-w-md text-sm text-[var(--mm-text2)]">
          <span className="mb-1 block text-xs text-[var(--mm-text3)]">Instance</span>
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
            ["rules", "Rules"],
            ["filters", "Filters"],
            ["schedule", "Schedule & limits"],
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
        {providerSection === "rules" ? (
          <div
            className="mm-card mm-dash-card border border-[var(--mm-border)] bg-[var(--mm-card-bg)] p-5 sm:p-6"
            data-testid={`pruner-provider-configuration-${provider}`}
            data-provider-section="rules"
          >
            <h3 className="text-base font-semibold text-[var(--mm-text1)]">Rules</h3>
            <p className="mt-1 text-sm leading-relaxed text-[var(--mm-text3)]">
              Deletion rules by medium. One save per column saves every rule in that column.
            </p>
            {!hasInstance ? (
              <p
                className="mt-4 rounded-md border border-dashed border-[var(--mm-border)] bg-[var(--mm-surface2)]/40 px-3 py-2 text-sm text-[var(--mm-text2)]"
                data-testid="pruner-provider-config-disabled-hint"
              >
                Save a connection first to enable these settings.
              </p>
            ) : null}
            <div
              className={`mt-6 grid gap-8 lg:grid-cols-2 lg:gap-10 ${!hasInstance ? "pointer-events-none opacity-45" : ""}`}
            >
              <div className="min-h-0 space-y-4" data-testid={`pruner-provider-tv-config-${provider}`}>
                <div className="flex items-center gap-2 border-b border-[var(--mm-border)] pb-2">
                  <span className="text-sm font-semibold uppercase tracking-wide text-[var(--mm-text1)]">TV</span>
                </div>
                <PrunerScopeTab
                  scope="tv"
                  variant="provider"
                  providerSubSection="rules"
                  disabledMode={!hasInstance}
                  contextOverride={activeCtx}
                />
              </div>
              <div className="min-h-0 space-y-4 lg:border-l lg:border-[var(--mm-border)] lg:pl-8" data-testid={`pruner-provider-movies-config-${provider}`}>
                <div className="flex items-center gap-2 border-b border-[var(--mm-border)] pb-2">
                  <span className="text-sm font-semibold uppercase tracking-wide text-[var(--mm-text1)]">Movies</span>
                </div>
                <PrunerScopeTab
                  scope="movies"
                  variant="provider"
                  providerSubSection="rules"
                  disabledMode={!hasInstance}
                  contextOverride={activeCtx}
                />
              </div>
            </div>
          </div>
        ) : null}

        {providerSection === "filters" ? (
          <div
            className="mm-card mm-dash-card border border-[var(--mm-border)] bg-[var(--mm-card-bg)] p-5 sm:p-6"
            data-testid={`pruner-provider-configuration-${provider}`}
            data-provider-section="filters"
          >
            <h3 className="text-base font-semibold text-[var(--mm-text1)]">Filters</h3>
            <p className="mt-1 text-sm leading-relaxed text-[var(--mm-text3)]">
              Optional preview narrowing. One save per column writes every filter in that column.
            </p>
            {!hasInstance ? (
              <p
                className="mt-4 rounded-md border border-dashed border-[var(--mm-border)] bg-[var(--mm-surface2)]/40 px-3 py-2 text-sm text-[var(--mm-text2)]"
                data-testid="pruner-provider-config-disabled-hint-filters"
              >
                Save a connection first to enable these settings.
              </p>
            ) : null}
            <div
              className={`mt-6 grid gap-8 lg:grid-cols-2 lg:gap-10 ${!hasInstance ? "pointer-events-none opacity-45" : ""}`}
            >
              <div className="min-h-0 space-y-4" data-testid={`pruner-provider-tv-filters-${provider}`}>
                <div className="flex items-center gap-2 border-b border-[var(--mm-border)] pb-2">
                  <span className="text-sm font-semibold uppercase tracking-wide text-[var(--mm-text1)]">TV</span>
                </div>
                <PrunerScopeTab
                  scope="tv"
                  variant="provider"
                  providerSubSection="filters"
                  disabledMode={!hasInstance}
                  contextOverride={activeCtx}
                />
              </div>
              <div className="min-h-0 space-y-4 lg:border-l lg:border-[var(--mm-border)] lg:pl-8" data-testid={`pruner-provider-movies-filters-${provider}`}>
                <div className="flex items-center gap-2 border-b border-[var(--mm-border)] pb-2">
                  <span className="text-sm font-semibold uppercase tracking-wide text-[var(--mm-text1)]">Movies</span>
                </div>
                <PrunerScopeTab
                  scope="movies"
                  variant="provider"
                  providerSubSection="filters"
                  disabledMode={!hasInstance}
                  contextOverride={activeCtx}
                />
              </div>
            </div>
          </div>
        ) : null}

        {providerSection === "schedule" ? (
          <div className="space-y-5" data-testid={`pruner-provider-configuration-${provider}`} data-provider-section="schedule">
            <div className="grid gap-6 lg:grid-cols-2 lg:gap-8">
              <div className="mm-card mm-dash-card flex min-h-[12rem] flex-col border border-[var(--mm-border)] bg-[var(--mm-card-bg)] p-5 sm:p-6">
                <h3 className="text-base font-semibold text-[var(--mm-text1)]">TV schedule & limits</h3>
                <p className="mt-1 text-sm text-[var(--mm-text3)]">Preview cap, scheduled previews, and manual previews for TV.</p>
                {!hasInstance ? (
                  <p className="mt-3 rounded-md border border-dashed border-[var(--mm-border)] bg-[var(--mm-surface2)]/40 px-3 py-2 text-sm text-[var(--mm-text2)]">
                    Save a connection first to enable these settings.
                  </p>
                ) : null}
                <div className={`mt-4 flex min-h-0 flex-1 flex-col ${!hasInstance ? "pointer-events-none opacity-45" : ""}`}>
                  <PrunerScopeTab
                    scope="tv"
                    variant="provider"
                    providerSubSection="schedule"
                    disabledMode={!hasInstance}
                    contextOverride={activeCtx}
                  />
                </div>
              </div>
              <div className="mm-card mm-dash-card flex min-h-[12rem] flex-col border border-[var(--mm-border)] bg-[var(--mm-card-bg)] p-5 sm:p-6">
                <h3 className="text-base font-semibold text-[var(--mm-text1)]">Movies schedule & limits</h3>
                <p className="mt-1 text-sm text-[var(--mm-text3)]">
                  Preview cap, scheduled previews, and manual previews for Movies.
                </p>
                {!hasInstance ? (
                  <p className="mt-3 rounded-md border border-dashed border-[var(--mm-border)] bg-[var(--mm-surface2)]/40 px-3 py-2 text-sm text-[var(--mm-text2)]">
                    Save a connection first to enable these settings.
                  </p>
                ) : null}
                <div className={`mt-4 flex min-h-0 flex-1 flex-col ${!hasInstance ? "pointer-events-none opacity-45" : ""}`}>
                  <PrunerScopeTab
                    scope="movies"
                    variant="provider"
                    providerSubSection="schedule"
                    disabledMode={!hasInstance}
                    contextOverride={activeCtx}
                  />
                </div>
              </div>
            </div>
          </div>
        ) : null}
      </div>
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
    const latestApplyLike = providerJobs?.find((j) => String(j.job_kind).toLowerCase().includes("apply")) ?? providerJobs?.[0];
    return { provider, rows, first, activeRules, latestPreview, latestJob: latestApplyLike };
  });

  return (
    <section className="space-y-6" data-testid="pruner-top-overview-tab">
      <header className="max-w-3xl">
        <h2 className="text-base font-semibold text-[var(--mm-text1)]">Overview</h2>
        <p className="mt-1 text-sm text-[var(--mm-text2)]">
          Use <strong className="text-[var(--mm-text)]">Connections</strong> for credentials and each provider tab for
          TV and Movies cleanup rules.
        </p>
      </header>

      <section
        className="mm-card mm-dash-card rounded-lg border border-[var(--mm-border)] bg-[var(--mm-card-bg)] px-4 py-5 sm:px-5"
        aria-labelledby="pruner-overview-at-a-glance-heading"
        data-testid="pruner-overview-at-a-glance"
      >
        <h2 id="pruner-overview-at-a-glance-heading" className="text-lg font-semibold text-[var(--mm-text1)]">
          At a glance
        </h2>
        <div className="mt-5 grid gap-4 sm:grid-cols-2 sm:gap-x-5 sm:gap-y-5 xl:grid-cols-3 xl:gap-x-5 xl:gap-y-5">
          {providerCards.map((card, i) => {
            const order = String(i + 1) as "1" | "2" | "3";
            const body = card.first ? (
              <div className="space-y-1.5">
                <p>
                  <span className="text-[var(--mm-text3)]">Connection test:</span>{" "}
                  <span className="font-medium text-[var(--mm-text1)]">
                    {card.first.last_connection_test_ok == null ? "Not run yet" : card.first.last_connection_test_ok ? "OK" : "Failed"}
                  </span>
                </p>
                <p>
                  <span className="text-[var(--mm-text3)]">Active rules:</span>{" "}
                  <span className="font-medium text-[var(--mm-text1)]">{card.activeRules}</span>
                </p>
                <p>
                  <span className="text-[var(--mm-text3)]">Last preview:</span>{" "}
                  <span className="font-medium text-[var(--mm-text1)]">
                    {card.latestPreview
                      ? `${card.latestPreview.media_scope.toUpperCase()} · ${card.latestPreview.last_preview_outcome ?? "—"}`
                      : "—"}
                  </span>
                </p>
                <p>
                  <span className="text-[var(--mm-text3)]">Last apply / job:</span>{" "}
                  <span className="font-medium text-[var(--mm-text1)]">
                    {card.latestJob ? `${card.latestJob.job_kind} (${card.latestJob.status})` : "—"}
                  </span>
                </p>
              </div>
            ) : (
              <p className="text-[var(--mm-text2)]">No instance registered. Add credentials under Connections.</p>
            );
            return <PrunerAtGlanceCard key={card.provider} glanceOrder={order} title={providerLabel(card.provider)} body={body} />;
          })}
        </div>
      </section>

      {instances.length === 0 ? (
        <div
          className="rounded-md border border-dashed border-[var(--mm-border)] bg-[var(--mm-surface2)]/35 px-4 py-4 text-sm text-[var(--mm-text2)]"
          data-testid="pruner-empty-state"
        >
          <p className="font-semibold text-[var(--mm-text1)]">No Emby, Jellyfin, or Plex instances registered yet.</p>
          <p className="mt-1">Open the Connections tab to add a server URL and API key or token.</p>
          <p className="mt-2 text-xs">Nothing is shared across providers or across instance rows.</p>
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
        Automatic preview schedules across providers. Each row is one instance and one scope (TV or Movies).
      </p>
      {instances.length === 0 ? (
        <p className="rounded-md border border-dashed border-[var(--mm-border)] bg-[var(--mm-surface2)]/35 px-4 py-3 text-sm text-[var(--mm-text2)]">
          No instances yet — no schedules to show.
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
        Recent Pruner jobs across providers. Provider linkage uses job payload when present.
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
        <p className="rounded-md border border-dashed border-[var(--mm-border)] bg-[var(--mm-surface2)]/35 px-4 py-3 text-sm text-[var(--mm-text2)]">
          No recent Pruner jobs.
        </p>
      ) : null}
      <p className="text-xs text-[var(--mm-text2)]">
        Apply removed/skipped/failed details are in{" "}
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
          Library cleanup for <strong className="text-[var(--mm-text)]">Emby</strong>,{" "}
          <strong className="text-[var(--mm-text)]">Jellyfin</strong>, and{" "}
          <strong className="text-[var(--mm-text)]">Plex</strong>. Use{" "}
          <strong className="text-[var(--mm-text)]">Connections</strong> for sign-in, then each provider tab for TV and
          Movies rules.
        </p>
      </header>

      <nav
        className="mt-3 flex flex-wrap gap-2.5 border-b border-[var(--mm-border)] pb-3.5 sm:mt-4"
        aria-label="Pruner sections"
        data-testid="pruner-top-level-tabs"
      >
        {([
          ["overview", "Overview"],
          ["connections", "Connections"],
          ["emby", "Emby"],
          ["jellyfin", "Jellyfin"],
          ["plex", "Plex"],
          ["schedules", "Schedules"],
          ["jobs", "Jobs"],
        ] as const).map(([id, label]) => (
          <button
            key={id}
            type="button"
            role="tab"
            aria-selected={topTab === id}
            className={fetcherSectionTabClass(topTab === id)}
            onClick={() => setTopTab(id)}
          >
            {label}
          </button>
        ))}
      </nav>

      <div className="mt-6 sm:mt-7" role="tabpanel" aria-label={
        (
          {
            overview: "Overview",
            connections: "Connections",
            emby: "Emby",
            jellyfin: "Jellyfin",
            plex: "Plex",
            schedules: "Schedules",
            jobs: "Jobs",
          } as const
        )[topTab]
      }>
        {q.isLoading ? <p className="text-sm text-[var(--mm-text2)]">Loading provider instances…</p> : null}
        {q.isError ? <p className="text-sm text-red-600">{(q.error as Error).message}</p> : null}
        {!q.isLoading && !q.isError ? (
          topTab === "overview" ? (
            <TopLevelOverview instances={instances} />
          ) : topTab === "connections" ? (
            <ConnectionsTabPanel allInstances={instances} />
          ) : topTab === "schedules" ? (
            <TopLevelSchedules instances={instances} />
          ) : topTab === "jobs" ? (
            <TopLevelJobs instances={instances} />
          ) : (
            <ProviderConfigurationWorkspace provider={topTab} allInstances={instances} />
          )
        ) : null}
      </div>
    </div>
  );
}
