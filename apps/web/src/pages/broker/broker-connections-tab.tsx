import { useEffect, useId, useState } from "react";
import { PageLoading } from "../../components/shared/page-loading";
import { MmListboxPicker } from "../../components/ui/mm-listbox-picker";
import {
  useBrokerManualSyncMutation,
  useBrokerSettingsQuery,
  useBrokerConnectionQuery,
  useRotateBrokerProxyKeyMutation,
  useUpdateBrokerConnectionMutation,
} from "../../lib/broker/broker-queries";
import { mmActionButtonClass } from "../../lib/ui/mm-control-roles";
import { useAppDateFormatter } from "../../lib/ui/mm-format-date";

const MASK = "\u2022".repeat(10);

const SYNC_OPTIONS = [
  { value: "full", label: "Full sync" },
  { value: "add_remove", label: "Add and remove only" },
] as const;

function brokerProxyTorznabUrl(apiKey: string): string {
  return `http://127.0.0.1:8788/api/v1/broker/torznab?apikey=${encodeURIComponent(apiKey)}`;
}

function brokerProxyNewznabUrl(apiKey: string): string {
  return `http://127.0.0.1:8788/api/v1/broker/newznab?apikey=${encodeURIComponent(apiKey)}`;
}

function CopyRow({ label, value }: { label: string; value: string }) {
  const [copied, setCopied] = useState(false);
  async function copy() {
    try {
      await navigator.clipboard.writeText(value);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 2000);
    } catch {
      /* ignore */
    }
  }
  return (
    <div className="mt-2">
      <p className="text-xs font-semibold uppercase tracking-wide text-[var(--mm-text3)]">{label}</p>
      <div className="mt-1 flex max-w-3xl flex-wrap gap-2">
        <input readOnly className="mm-input min-w-0 flex-1 font-mono text-xs" value={value} />
        <button type="button" className={mmActionButtonClass({ variant: "secondary" })} onClick={() => void copy()}>
          {copied ? "Copied" : "Copy"}
        </button>
      </div>
    </div>
  );
}

function syncStatusDotClass(lastOk: boolean | null): string {
  if (lastOk === true) return "bg-emerald-500";
  if (lastOk === false) return "bg-red-500";
  return "bg-[var(--mm-text3)]";
}

function ArrConnectionCard({
  title,
  arrType,
  canOperate,
}: {
  title: string;
  arrType: "sonarr" | "radarr";
  canOperate: boolean;
}) {
  const q = useBrokerConnectionQuery(arrType);
  const put = useUpdateBrokerConnectionMutation();
  const sync = useBrokerManualSyncMutation(arrType);
  const fmt = useAppDateFormatter();
  const baseId = useId();

  const [url, setUrl] = useState("");
  const [apiKey, setApiKey] = useState("");
  const [showKey, setShowKey] = useState(false);
  const [syncMode, setSyncMode] = useState<string>("full");
  const [saveOk, setSaveOk] = useState(false);
  const [saveErr, setSaveErr] = useState<string | null>(null);

  useEffect(() => {
    if (!q.data) {
      return;
    }
    setUrl(q.data.url ?? "");
    setApiKey("");
    setSyncMode(q.data.sync_mode === "add_remove" ? "add_remove" : "full");
  }, [q.data]);

  if (q.isPending) {
    return <p className="text-sm text-[var(--mm-text2)]">Loading…</p>;
  }
  if (q.isError) {
    return <p className="text-sm text-red-400">{(q.error as Error).message}</p>;
  }

  const row = q.data;

  async function onSave() {
    setSaveOk(false);
    setSaveErr(null);
    try {
      const payload: { url: string; sync_mode: string; api_key?: string } = {
        url: url.trim(),
        sync_mode: syncMode,
      };
      if (apiKey.trim()) {
        payload.api_key = apiKey.trim();
      }
      await put.mutateAsync({ arrType, data: payload });
      setApiKey("");
      setSaveOk(true);
      window.setTimeout(() => setSaveOk(false), 2500);
    } catch (e) {
      setSaveErr((e as Error).message);
    }
  }

  return (
    <section
      className="mm-card flex h-full min-h-0 flex-col border border-[var(--mm-border)] bg-[var(--mm-card-bg)] p-4 shadow-sm sm:p-5"
      data-testid={arrType === "sonarr" ? "broker-connections-sonarr" : "broker-connections-radarr"}
    >
      <h2 className="text-base font-semibold text-[var(--mm-text1)]">{title}</h2>
      <div className="mt-3 flex min-h-0 flex-1 flex-col gap-3">
        <label className="block">
          <span className="text-xs font-medium text-[var(--mm-text2)]">URL</span>
          <input
            id={`${baseId}-url`}
            className="mm-input mt-1 w-full"
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            autoComplete="off"
            disabled={!canOperate}
          />
        </label>
        <div>
          <label className="text-xs font-medium text-[var(--mm-text2)]" htmlFor={`${baseId}-key`}>
            API key
          </label>
          <div className="mt-1 flex flex-wrap items-center gap-2">
            <input
              id={`${baseId}-key`}
              className="mm-input min-w-0 flex-1 font-mono text-sm"
              type={showKey ? "text" : "password"}
              autoComplete="off"
              placeholder={MASK}
              value={apiKey}
              onChange={(e) => setApiKey(e.target.value)}
              disabled={!canOperate}
            />
            <button
              type="button"
              className={mmActionButtonClass({ variant: "secondary", disabled: !canOperate })}
              disabled={!canOperate}
              onClick={() => setShowKey((v) => !v)}
            >
              {showKey ? "Hide" : "Show"}
            </button>
          </div>
        </div>
        <label className="block">
          <span id={`${baseId}-sync-label`} className="text-xs font-semibold uppercase tracking-wide text-[var(--mm-text3)]">
            Sync mode
          </span>
          <MmListboxPicker
            className="mt-1.5"
            ariaLabelledBy={`${baseId}-sync-label`}
            options={SYNC_OPTIONS.map((o) => ({ value: o.value, label: o.label }))}
            value={syncMode}
            onChange={(v) => setSyncMode(v)}
            disabled={!canOperate}
          />
        </label>
        <div className="mt-auto border-t border-[var(--mm-border)] pt-3 text-sm">
          <div className="flex flex-wrap items-center gap-2 text-[var(--mm-text2)]">
            <span className={`inline-block h-2 w-2 shrink-0 rounded-full ${syncStatusDotClass(row.last_sync_ok)}`} aria-hidden />
            <span className="text-xs text-[var(--mm-text3)]">Last synced</span>
            <span className="font-medium text-[var(--mm-text1)]">{row.last_synced_at ? fmt(row.last_synced_at) : "Never"}</span>
          </div>
          {row.last_sync_ok === false && row.last_sync_error ? (
            <p className="mt-1 text-xs text-red-400">{row.last_sync_error}</p>
          ) : null}
        </div>
        <div className="flex flex-wrap gap-2 border-t border-[var(--mm-border)] pt-3">
          <button
            type="button"
            className={mmActionButtonClass({ variant: "primary", disabled: !canOperate || put.isPending })}
            disabled={!canOperate || put.isPending}
            onClick={() => void onSave()}
          >
            {put.isPending ? "Saving…" : "Save"}
          </button>
          <button
            type="button"
            className={mmActionButtonClass({ variant: "secondary", disabled: !canOperate || sync.isPending })}
            disabled={!canOperate || sync.isPending}
            onClick={() => void sync.mutateAsync().catch(() => {})}
          >
            {sync.isPending ? "Enqueuing…" : arrType === "sonarr" ? "Sync to Sonarr" : "Sync to Radarr"}
          </button>
        </div>
        {saveErr ? (
          <p className="text-sm text-red-400" role="alert">
            {saveErr}
          </p>
        ) : null}
        {saveOk ? (
          <p className="text-sm text-emerald-600" role="status">
            Saved.
          </p>
        ) : null}
      </div>
    </section>
  );
}

export function BrokerConnectionsTab({ canOperate }: { canOperate: boolean }) {
  const settings = useBrokerSettingsQuery();
  const rotate = useRotateBrokerProxyKeyMutation();
  const [rotateErr, setRotateErr] = useState<string | null>(null);

  if (settings.isPending) {
    return <PageLoading />;
  }
  if (settings.isError) {
    return <p className="text-sm text-red-400">{(settings.error as Error).message}</p>;
  }

  const key = settings.data?.proxy_api_key ?? "";

  async function onRotate() {
    if (!window.confirm("Rotate the Broker proxy API key? Sonarr and Radarr must be updated with the new key.")) {
      return;
    }
    setRotateErr(null);
    try {
      await rotate.mutateAsync();
    } catch (e) {
      setRotateErr((e as Error).message);
    }
  }

  return (
    <div className="mm-bubble-stack" data-testid="broker-connections-tab">
      <div className="grid gap-5 lg:grid-cols-2 lg:gap-6">
        <ArrConnectionCard title="Sonarr" arrType="sonarr" canOperate={canOperate} />
        <ArrConnectionCard title="Radarr" arrType="radarr" canOperate={canOperate} />
      </div>

      <section className="mm-card border border-[var(--mm-border)] bg-[var(--mm-card-bg)] p-4 shadow-sm sm:p-5" data-testid="broker-connections-proxy">
        <h2 className="text-base font-semibold text-[var(--mm-text1)]">Proxy API key</h2>
        <div className="mt-3 space-y-3 text-sm text-[var(--mm-text2)]">
          <p>
            Use this key to point Sonarr or Radarr at Broker as a single unified indexer. Copy the Torznab or Newznab URL into
            your *arr indexer settings.
          </p>
          <CopyRow label="API key" value={key} />
          <CopyRow label="Torznab URL" value={brokerProxyTorznabUrl(key)} />
          <CopyRow label="Newznab URL" value={brokerProxyNewznabUrl(key)} />
          {rotateErr ? (
            <p className="text-sm text-red-400" role="alert">
              {rotateErr}
            </p>
          ) : null}
          <button
            type="button"
            className={mmActionButtonClass({ variant: "secondary", disabled: !canOperate || rotate.isPending })}
            disabled={!canOperate || rotate.isPending}
            onClick={() => void onRotate()}
          >
            {rotate.isPending ? "Rotating…" : "Rotate key"}
          </button>
        </div>
      </section>
    </div>
  );
}
