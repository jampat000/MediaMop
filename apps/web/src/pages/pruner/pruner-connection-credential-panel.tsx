import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";
import { mmActionButtonClass } from "../../lib/ui/mm-control-roles";
import { useMeQuery } from "../../lib/auth/queries";
import type { PrunerServerInstance } from "../../lib/pruner/api";
import {
  patchPrunerInstance,
  postPrunerConnectionTest,
  postPrunerInstance,
} from "../../lib/pruner/api";
import { formatPrunerDateTime } from "./pruner-ui-utils";
import type { ProviderTab } from "./pruner-page-types";
import { providerLabel } from "./pruner-page-utils";

type PrunerConnectionCredentialPanelProps = {
  provider: ProviderTab;
  allInstances: PrunerServerInstance[];
  /** When set, instance row is chosen by the parent (e.g. provider workspace) so Connection matches Cleanup. */
  instanceSelection?: {
    selectedId: number | null;
    onSelectedIdChange: (id: number | null) => void;
  };
};

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

function prunerConnectionPlaceholderUrl(provider: ProviderTab): string {
  if (provider === "plex") return "http://localhost:32400";
  return "http://localhost:8096";
}

export function PrunerConnectionCredentialPanel({
  provider,
  allInstances,
  instanceSelection,
}: PrunerConnectionCredentialPanelProps) {
  const me = useMeQuery();
  const q = useQueryClient();
  const canOperate = me.data?.role === "admin" || me.data?.role === "operator";
  const providerName = providerLabel(provider);
  const providerInstances = useMemo(
    () => allInstances.filter((x) => x.provider === provider),
    [allInstances, provider],
  );
  const firstProviderInstanceId = providerInstances[0]?.id ?? null;
  const [internalSelectedInstanceId, setInternalSelectedInstanceId] = useState<
    number | null
  >(firstProviderInstanceId);
  const controlled = Boolean(instanceSelection);
  const selectedInstanceId = controlled
    ? instanceSelection!.selectedId
    : internalSelectedInstanceId;
  const setSelectedInstanceId = controlled
    ? instanceSelection!.onSelectedIdChange
    : setInternalSelectedInstanceId;
  const selectedInstance =
    providerInstances.find((x) => x.id === selectedInstanceId) ??
    providerInstances[0];
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
  const dirty = prunerConnectionDirty(
    hasInstance,
    savedUrl,
    baseUrlDraft,
    credentialDraft,
  );
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
    setInternalSelectedInstanceId(firstProviderInstanceId);
  }, [controlled, firstProviderInstanceId]);

  useEffect(() => {
    setBaseUrlDraft(selectedInstance?.base_url ?? "");
    setCredentialDraft("");
    setShowCredential(false);
    setErr(null);
    setSaveJustSucceeded(false);
    setTestJustSucceeded(false);
  }, [provider, selectedInstance?.id, selectedInstance?.base_url]);

  async function saveConnection() {
    setSavePending(true);
    setErr(null);
    setSaveJustSucceeded(false);
    setTestJustSucceeded(false);
    try {
      const trimmedUrl = baseUrlDraft.trim();
      if (!trimmedUrl) throw new Error("Base URL is required.");
      if (!hasInstance && !credentialDraft.trim()) {
        throw new Error(
          `${providerCredentialLabel(provider)} is required to create a new ${providerName} connection.`,
        );
      }
      const credentialKey = provider === "plex" ? "auth_token" : "api_key";
      const credentials = credentialDraft.trim()
        ? { [credentialKey]: credentialDraft.trim() }
        : undefined;
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

  const saveLabel = saveJustSucceeded ? "Saved" : `Save ${providerName}`;
  const testLabel = testJustSucceeded
    ? "Test complete"
    : `Test ${providerName}`;

  return (
    <section
      className="mm-card mm-dash-card p-6"
      data-testid={`pruner-connection-panel-${provider}`}
    >
      <div className="mm-bubble-stack">
        <h3 className="text-base font-semibold text-[var(--mm-text1)]">
          {providerName} connection
        </h3>
        <p className="text-sm text-[var(--mm-text2)]">
          Add a server URL and {providerCredentialLabel(provider)} for this
          provider.
        </p>
        {providerInstances.length > 1 ? (
          <label className="block text-sm text-[var(--mm-text2)]">
            <span className="mb-1 block text-xs text-[var(--mm-text3)]">
              Server
            </span>
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
      </div>

      <div className="mt-4 grid gap-3 sm:grid-cols-2">
        <label className="block">
          <span className="text-xs text-[var(--mm-text3)]">Base URL</span>
          <input
            className="mm-input mt-1 w-full"
            value={baseUrlDraft}
            placeholder={prunerConnectionPlaceholderUrl(provider)}
            onChange={(e) => setBaseUrlDraft(e.target.value)}
            disabled={!canOperate || panelBusy}
          />
        </label>
        <label className="block">
          <span className="text-xs text-[var(--mm-text3)]">
            {providerCredentialLabel(provider)}
          </span>
          <div className="mt-1 flex items-center gap-2">
            <input
              className="mm-input w-full"
              type={showCredential ? "text" : "password"}
              value={credentialDraft}
              placeholder={credentialPlaceholder}
              onChange={(e) => setCredentialDraft(e.target.value)}
              disabled={!canOperate || panelBusy}
              autoComplete="off"
            />
            <button
              type="button"
              className={mmActionButtonClass({
                variant: "secondary",
                disabled: !canOperate || panelBusy,
              })}
              disabled={!canOperate || panelBusy}
              onClick={() => setShowCredential((s) => !s)}
            >
              {showCredential ? "Hide" : "Show"}
            </button>
          </div>
        </label>
      </div>

      <div className="mt-4 flex flex-wrap gap-2">
        <button
          type="button"
          className={mmActionButtonClass({
            variant: "primary",
            disabled: !canOperate || !dirty || panelBusy,
          })}
          disabled={!canOperate || !dirty || panelBusy}
          onClick={() => void saveConnection()}
        >
          {savePending ? "Saving..." : saveLabel}
        </button>
        <button
          type="button"
          className={mmActionButtonClass({
            variant: "secondary",
            disabled: !canOperate || panelBusy || !selectedInstance,
          })}
          disabled={!canOperate || panelBusy || !selectedInstance}
          onClick={() => void runConnectionTest()}
        >
          {testPending ? "Testing..." : testLabel}
        </button>
      </div>

      <div
        className="mt-4 rounded-md border border-[var(--mm-border)] bg-[var(--mm-card-bg)] p-3.5 text-sm text-[var(--mm-text2)]"
        data-testid={`pruner-connection-status-${provider}`}
      >
        <p className="text-sm font-medium text-[var(--mm-text1)]">
          {connectionStatusMain}
        </p>
        <p className="mt-1 text-xs text-[var(--mm-text3)]">
          Last completed check:{" "}
          {formatPrunerDateTime(
            selectedInstance?.last_connection_test_at ?? null,
          )}
        </p>
        {selectedInstance?.last_connection_test_detail &&
        selectedInstance.last_connection_test_ok !== true ? (
          <p className="mt-1 text-xs text-[var(--mm-text3)]">
            {selectedInstance.last_connection_test_detail}
          </p>
        ) : null}
        {err ? (
          <p className="mt-2 text-sm text-red-400" role="alert">
            {err}
          </p>
        ) : null}
        <p className="mt-2 text-xs text-[var(--mm-text3)]">
          Each test adds a line to{" "}
          <Link
            to="/activity"
            className="text-[var(--mm-accent)] underline-offset-2 hover:underline"
          >
            Activity
          </Link>{" "}
          for your records.
        </p>
      </div>
    </section>
  );
}
