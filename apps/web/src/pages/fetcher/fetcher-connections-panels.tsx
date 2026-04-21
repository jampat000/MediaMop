import { useEffect, useState, type Dispatch, type SetStateAction } from "react";
import { Link } from "react-router-dom";
import { PageLoading } from "../../components/shared/page-loading";
import { isHttpErrorFromApi, isLikelyNetworkFailure } from "../../lib/api/error-guards";
import {
  useFetcherArrConnectionRadarrSaveMutation,
  useFetcherArrConnectionSonarrSaveMutation,
  useFetcherArrConnectionTestMutation,
  useFetcherArrOperatorSettingsQuery,
} from "../../lib/fetcher/arr-operator-settings/queries";
import type { FetcherArrConnectionPanel } from "../../lib/fetcher/arr-operator-settings/types";
import { showFetcherArrOperatorSettingsEditor } from "../../lib/fetcher/failed-imports/eligibility";
import {
  FETCHER_CONNECTION_PANEL_RADARR,
  FETCHER_CONNECTION_PANEL_SONARR,
  FETCHER_SAVE_RADARR,
  FETCHER_SAVE_SONARR,
  FETCHER_TEST_RADARR,
  FETCHER_TEST_SONARR,
} from "./fetcher-display-names";
import { FetcherEnableSwitch } from "./fetcher-enable-switch";
import { fetcherMenuButtonClass } from "./fetcher-menu-button";

/** Placeholder when a key is stored server-side (empty field = unchanged). */
const API_KEY_SAVED_PLACEHOLDER = "\u2022".repeat(10);

type Draft = {
  enabled: boolean;
  base_url: string;
  api_key: string;
};

function liftDraftSetter(set: Dispatch<SetStateAction<Draft | null>>): Dispatch<SetStateAction<Draft>> {
  return (u) =>
    set((prev) => {
      if (prev === null) {
        return null;
      }
      return typeof u === "function" ? (u as (d: Draft) => Draft)(prev) : u;
    });
}

function cloneDraft(panel: FetcherArrConnectionPanel): Draft {
  return {
    enabled: panel.enabled,
    base_url: panel.base_url,
    api_key: "",
  };
}

function draftsDirty(panel: FetcherArrConnectionPanel, draft: Draft): boolean {
  if (draft.enabled !== panel.enabled) {
    return true;
  }
  if (draft.base_url.trim() !== (panel.base_url || "").trim()) {
    return true;
  }
  if (draft.api_key.trim() !== "") {
    return true;
  }
  return false;
}

function ConnectionEffectiveNote({
  panel,
  appLabel,
}: {
  panel: FetcherArrConnectionPanel;
  appLabel: string;
}) {
  const saved = (panel.base_url || "").trim();
  const eff = (panel.effective_base_url || "").trim();

  if (!panel.enabled) {
    return null;
  }

  if (saved && eff && saved !== eff) {
    return (
      <p className="text-xs leading-relaxed text-[var(--mm-text3)]">
        <strong>In use now:</strong> {eff} — this differs from the address saved above, so MediaMop is taking the
        address (and sign-in) from your server file until this link is complete here.
      </p>
    );
  }

  if (panel.enabled && saved && !panel.api_key_is_saved) {
    return (
      <p className="text-xs leading-relaxed text-[var(--mm-text3)]">
        The address is saved, but there is no saved key here yet. MediaMop is using the server file for sign-in (and
        may use its address too) until you save a key above.
      </p>
    );
  }

  if (panel.enabled && !saved && eff) {
    return (
      <p className="text-xs leading-relaxed text-[var(--mm-text3)]">
        No address is saved here yet. With this link On, MediaMop is using the server file for {appLabel} until you
        save an address and key above.
      </p>
    );
  }

  return null;
}

function ConnectionPanel({
  title,
  app,
  appLabel,
  panel,
  draft,
  setDraft,
  showKey,
  setShowKey,
  canEdit,
  savePending,
  testPendingThis,
  statusMessage,
  saveJustSucceeded,
  testJustSucceeded,
  onSave,
  onTest,
  placeholderUrl,
}: {
  title: string;
  app: "sonarr" | "radarr";
  appLabel: string;
  panel: FetcherArrConnectionPanel;
  draft: Draft;
  setDraft: Dispatch<SetStateAction<Draft>>;
  showKey: boolean;
  setShowKey: Dispatch<SetStateAction<boolean>>;
  canEdit: boolean;
  savePending: boolean;
  testPendingThis: boolean;
  statusMessage: string | null;
  saveJustSucceeded: boolean;
  testJustSucceeded: boolean;
  onSave: () => void;
  onTest: () => void;
  placeholderUrl: string;
}) {
  const saveLabel = app === "sonarr" ? FETCHER_SAVE_SONARR : FETCHER_SAVE_RADARR;
  const testLabel = app === "sonarr" ? FETCHER_TEST_SONARR : FETCHER_TEST_RADARR;
  const dirty = draftsDirty(panel, draft);
  const panelBusy = savePending || testPendingThis;
  const apiKeyPlaceholder =
    panel.api_key_is_saved && draft.api_key === "" ? API_KEY_SAVED_PLACEHOLDER : "Enter API key";

  return (
    <section
      className={[
        "mm-card mm-dash-card mm-bubble-stack flex h-full min-h-0 min-w-0 flex-col transition-shadow duration-200",
        saveJustSucceeded
          ? "ring-2 ring-[var(--mm-accent-ring)] ring-offset-2 ring-offset-[var(--mm-bg-main)] shadow-[0_0_0_1px_rgba(212,175,55,0.12)]"
          : "",
      ].join(" ")}
      data-testid={`fetcher-connection-panel-${app}`}
    >
      <h3 className="text-base font-semibold text-[var(--mm-text1)]">{title}</h3>

      <FetcherEnableSwitch
        id={`fetcher-conn-enable-${app}`}
        label="Enable / Disable"
        enabled={draft.enabled}
        disabled={!canEdit || panelBusy}
        onChange={(v) => setDraft((d) => ({ ...d, enabled: v }))}
      />

      <label className="block text-sm text-[var(--mm-text2)]">
        <span className="mb-1 block text-xs text-[var(--mm-text3)]">Base URL</span>
        <input
          type="url"
          autoComplete="off"
          placeholder={placeholderUrl}
          className="mm-input w-full"
          disabled={!canEdit || panelBusy}
          value={draft.base_url}
          onChange={(e) => setDraft((d) => ({ ...d, base_url: e.target.value }))}
        />
      </label>
      <ConnectionEffectiveNote panel={panel} appLabel={appLabel} />

      <div className="space-y-1">
        <label className="block text-sm text-[var(--mm-text2)]" htmlFor={`fetcher-conn-key-${app}`}>
          <span className="mb-1 block text-xs text-[var(--mm-text3)]">API key</span>
        </label>
        <div className="flex flex-wrap gap-2">
          <input
            id={`fetcher-conn-key-${app}`}
            type={showKey ? "text" : "password"}
            autoComplete="new-password"
            placeholder={apiKeyPlaceholder}
            className="mm-input min-w-[12rem] flex-1 text-sm tracking-normal text-[var(--mm-text)]"
            disabled={!canEdit || panelBusy}
            value={draft.api_key}
            aria-describedby={panel.api_key_is_saved ? `fetcher-conn-key-hint-${app}` : undefined}
            onChange={(e) => {
              const next = e.target.value;
              setDraft((d) => ({ ...d, api_key: next }));
              if (next.trim() === "") {
                setShowKey(false);
              }
            }}
          />
          <button
            type="button"
            className={fetcherMenuButtonClass({
              variant: "tertiary",
              disabled: !canEdit || panelBusy,
            })}
            disabled={!canEdit || panelBusy}
            onClick={() => setShowKey((v) => !v)}
          >
            {showKey ? "Hide" : "Show"}
          </button>
        </div>
        {panel.api_key_is_saved ? (
          <p id={`fetcher-conn-key-hint-${app}`} className="text-xs text-[var(--mm-text3)]">
            Leave blank to keep your saved key, or type a new one to replace it.
          </p>
        ) : null}
      </div>

      {saveJustSucceeded ? (
        <p
          className="rounded-md border border-[rgba(212,175,55,0.45)] bg-[var(--mm-accent-soft)] px-3 py-2 text-sm font-medium text-[var(--mm-text1)]"
          role="status"
          data-testid={`fetcher-connection-save-ok-${app}`}
        >
          Saved.
        </p>
      ) : null}

      {testJustSucceeded ? (
        <p
          className="rounded-md border border-[rgba(212,175,55,0.45)] bg-[var(--mm-accent-soft)] px-3 py-2 text-sm font-medium text-[var(--mm-text1)]"
          role="status"
          data-testid={`fetcher-connection-test-ok-${app}`}
        >
          Test succeeded.
        </p>
      ) : null}

      <div className="flex flex-wrap items-center gap-3">
        <button
          type="button"
          className={fetcherMenuButtonClass({
            variant: "primary",
            disabled: !canEdit || !dirty || panelBusy,
          })}
          disabled={!canEdit || !dirty || panelBusy}
          onClick={onSave}
        >
          {savePending ? "Saving…" : saveLabel}
        </button>
        <button
          type="button"
          className={fetcherMenuButtonClass({
            variant: "secondary",
            disabled: !canEdit || panelBusy,
          })}
          disabled={!canEdit || panelBusy}
          onClick={onTest}
        >
          {testPendingThis ? "Testing…" : testLabel}
        </button>
      </div>

      <div
        className="mt-auto rounded-md border border-[var(--mm-border)] bg-[var(--mm-card-bg)] p-3.5 text-sm text-[var(--mm-text2)]"
        data-testid={`fetcher-connection-status-${app}`}
      >
        <p className="font-medium text-[var(--mm-text1)]">{panel.status_headline}</p>
        {panel.last_test_detail && panel.status_headline !== "Connection status: OK" ? (
          <p className="mt-1 text-xs text-[var(--mm-text3)]">{panel.last_test_detail}</p>
        ) : null}
        {statusMessage ? (
          <p className="mt-2 text-sm text-red-400" role="alert">
            {statusMessage}
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

/** Connections tab — Sonarr then Radarr; editable credentials with encrypted storage on the server. */
export function FetcherConnectionsPanels({ role }: { role: string | undefined }) {
  const q = useFetcherArrOperatorSettingsQuery();
  const saveSonarr = useFetcherArrConnectionSonarrSaveMutation();
  const saveRadarr = useFetcherArrConnectionRadarrSaveMutation();
  const testConn = useFetcherArrConnectionTestMutation();
  const canEdit = showFetcherArrOperatorSettingsEditor(role);

  const [sonarrDraft, setSonarrDraft] = useState<Draft | null>(null);
  const [radarrDraft, setRadarrDraft] = useState<Draft | null>(null);
  const [sonarrShowKey, setSonarrShowKey] = useState(false);
  const [radarrShowKey, setRadarrShowKey] = useState(false);
  const [sonarrMsg, setSonarrMsg] = useState<string | null>(null);
  const [radarrMsg, setRadarrMsg] = useState<string | null>(null);
  const [sonarrSaveOk, setSonarrSaveOk] = useState(false);
  const [radarrSaveOk, setRadarrSaveOk] = useState(false);
  const [sonarrTestOk, setSonarrTestOk] = useState(false);
  const [radarrTestOk, setRadarrTestOk] = useState(false);
  const [testingApp, setTestingApp] = useState<"sonarr" | "radarr" | null>(null);

  useEffect(() => {
    if (!q.data) {
      return;
    }
    setSonarrDraft((prev) => {
      if (prev === null) {
        return cloneDraft(q.data.sonarr_connection);
      }
      if (!draftsDirty(q.data.sonarr_connection, prev)) {
        return cloneDraft(q.data.sonarr_connection);
      }
      return prev;
    });
    setRadarrDraft((prev) => {
      if (prev === null) {
        return cloneDraft(q.data.radarr_connection);
      }
      if (!draftsDirty(q.data.radarr_connection, prev)) {
        return cloneDraft(q.data.radarr_connection);
      }
      return prev;
    });
  }, [q.data]);

  useEffect(() => {
    if (!sonarrSaveOk) {
      return;
    }
    const t = window.setTimeout(() => setSonarrSaveOk(false), 2400);
    return () => clearTimeout(t);
  }, [sonarrSaveOk]);

  useEffect(() => {
    if (!radarrSaveOk) {
      return;
    }
    const t = window.setTimeout(() => setRadarrSaveOk(false), 2400);
    return () => clearTimeout(t);
  }, [radarrSaveOk]);

  useEffect(() => {
    if (!sonarrTestOk) {
      return;
    }
    const t = window.setTimeout(() => setSonarrTestOk(false), 2400);
    return () => clearTimeout(t);
  }, [sonarrTestOk]);

  useEffect(() => {
    if (!radarrTestOk) {
      return;
    }
    const t = window.setTimeout(() => setRadarrTestOk(false), 2400);
    return () => clearTimeout(t);
  }, [radarrTestOk]);

  const onSaveSonarr = () => {
    if (!sonarrDraft) {
      return;
    }
    setSonarrMsg(null);
    setSonarrSaveOk(false);
    setSonarrTestOk(false);
    saveSonarr.mutate(
      {
        enabled: sonarrDraft.enabled,
        base_url: sonarrDraft.base_url,
        api_key: sonarrDraft.api_key,
      },
      {
        onSuccess: () => {
          setSonarrSaveOk(true);
          setSonarrShowKey(false);
        },
        onError: (e) => setSonarrMsg(e instanceof Error ? e.message : "Could not save."),
      },
    );
  };

  const onSaveRadarr = () => {
    if (!radarrDraft) {
      return;
    }
    setRadarrMsg(null);
    setRadarrSaveOk(false);
    setRadarrTestOk(false);
    saveRadarr.mutate(
      {
        enabled: radarrDraft.enabled,
        base_url: radarrDraft.base_url,
        api_key: radarrDraft.api_key,
      },
      {
        onSuccess: () => {
          setRadarrSaveOk(true);
          setRadarrShowKey(false);
        },
        onError: (e) => setRadarrMsg(e instanceof Error ? e.message : "Could not save."),
      },
    );
  };

  const runTest = (app: "sonarr" | "radarr") => {
    const draft = app === "sonarr" ? sonarrDraft : radarrDraft;
    if (!draft) {
      return;
    }
    if (app === "sonarr") {
      setSonarrMsg(null);
      setSonarrSaveOk(false);
      setSonarrTestOk(false);
    } else {
      setRadarrMsg(null);
      setRadarrSaveOk(false);
      setRadarrTestOk(false);
    }
    setTestingApp(app);
    testConn.mutate(
      {
        app,
        enabled: draft.enabled,
        base_url: draft.base_url,
        api_key: draft.api_key,
      },
      {
        onSettled: () => {
          setTestingApp(null);
        },
        onSuccess: (data) => {
          if (data.ok) {
            if (app === "sonarr") {
              setSonarrMsg(null);
              setSonarrTestOk(true);
              setSonarrShowKey(false);
            } else {
              setRadarrMsg(null);
              setRadarrTestOk(true);
              setRadarrShowKey(false);
            }
          } else if (app === "sonarr") {
            setSonarrMsg(data.message);
          } else {
            setRadarrMsg(data.message);
          }
        },
        onError: (e) =>
          app === "sonarr"
            ? setSonarrMsg(e instanceof Error ? e.message : "Check failed.")
            : setRadarrMsg(e instanceof Error ? e.message : "Check failed."),
      },
    );
  };

  if (q.isPending || !sonarrDraft || !radarrDraft || !q.data) {
    return <PageLoading label="Loading connections" />;
  }

  if (q.isError) {
    return (
      <p className="text-sm text-red-400" role="alert">
        {isLikelyNetworkFailure(q.error)
          ? "Could not reach the MediaMop API."
          : isHttpErrorFromApi(q.error)
            ? "The server refused this request."
            : "Could not load connections."}
      </p>
    );
  }

  return (
    <section
      className="mm-fetcher-module-surface"
      aria-labelledby="mm-fetcher-connections-heading"
      data-testid="fetcher-connections-panels"
    >
      <h2 id="mm-fetcher-connections-heading" className="sr-only">
        Fetcher connections
      </h2>

      <div className="mm-dash-grid" data-testid="fetcher-connection-panels-grid">
        <ConnectionPanel
          title={FETCHER_CONNECTION_PANEL_SONARR}
          app="sonarr"
          appLabel="Sonarr"
          panel={q.data.sonarr_connection}
          draft={sonarrDraft}
          setDraft={liftDraftSetter(setSonarrDraft)}
          showKey={sonarrShowKey}
          setShowKey={setSonarrShowKey}
          canEdit={canEdit}
          savePending={saveSonarr.isPending}
          testPendingThis={testingApp === "sonarr" && testConn.isPending}
          statusMessage={sonarrMsg}
          saveJustSucceeded={sonarrSaveOk}
          testJustSucceeded={sonarrTestOk}
          onSave={onSaveSonarr}
          onTest={() => runTest("sonarr")}
          placeholderUrl="http://localhost:8989"
        />
        <ConnectionPanel
          title={FETCHER_CONNECTION_PANEL_RADARR}
          app="radarr"
          appLabel="Radarr"
          panel={q.data.radarr_connection}
          draft={radarrDraft}
          setDraft={liftDraftSetter(setRadarrDraft)}
          showKey={radarrShowKey}
          setShowKey={setRadarrShowKey}
          canEdit={canEdit}
          savePending={saveRadarr.isPending}
          testPendingThis={testingApp === "radarr" && testConn.isPending}
          statusMessage={radarrMsg}
          saveJustSucceeded={radarrSaveOk}
          testJustSucceeded={radarrTestOk}
          onSave={onSaveRadarr}
          onTest={() => runTest("radarr")}
          placeholderUrl="http://localhost:7878"
        />
      </div>
    </section>
  );
}
