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
    <div className="mt-3">
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
  const syncOkIcon = row.last_sync_ok === true ? "✓" : row.last_sync_ok === false ? "✗" : "—";
  const syncOkClass =
    row.last_sync_ok === true ? "text-emerald-500" : row.last_sync_ok === false ? "text-red-400" : "text-[var(--mm-text3)]";

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
      className="mm-card mm-dash-card mm-fetcher-module-surface"
      data-testid={arrType === "sonarr" ? "broker-connections-sonarr" : "broker-connections-radarr"}
    >
      <h2 className="mm-card__title text-lg">{title}</h2>
      <div className="mm-card__body mt-5 space-y-4">
        <label className="block">
          <span className="text-sm font-medium text-[var(--mm-text)]">URL</span>
          <input
            id={`${baseId}-url`}
            className="mm-input mt-1 w-full max-w-2xl"
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            autoComplete="off"
            disabled={!canOperate}
          />
        </label>
        <div>
          <label className="text-sm font-medium text-[var(--mm-text)]" htmlFor={`${baseId}-key`}>
            API key
          </label>
          <div className="mt-1 flex max-w-2xl flex-wrap items-center gap-2">
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
          <p className="mt-1 text-xs text-[var(--mm-text3)]">Saved keys are never shown again after you leave this page.</p>
        </div>
        <label className="block max-w-xl">
          <span id={`${baseId}-sync-label`} className="text-xs font-semibold uppercase tracking-wide text-[var(--mm-text3)]">
            Sync mode
          </span>
          <MmListboxPicker
            className="mt-2"
            ariaLabelledBy={`${baseId}-sync-label`}
            options={SYNC_OPTIONS.map((o) => ({ value: o.value, label: o.label }))}
            value={syncMode}
            onChange={(v) => setSyncMode(v)}
            disabled={!canOperate}
          />
        </label>
        <div className="rounded-md border border-[var(--mm-border)] bg-black/10 px-4 py-3 text-sm">
          <p>
            <span className="text-[var(--mm-text3)]">Last synced:</span>{" "}
            <span className="font-medium text-[var(--mm-text1)]">
              {row.last_synced_at ? fmt(row.last_synced_at) : "Never"}
            </span>
          </p>
          <p className="mt-2">
            <span className="text-[var(--mm-text3)]">Last sync status:</span>{" "}
            <span className={`font-semibold ${syncOkClass}`}>{syncOkIcon}</span>
            {row.last_sync_ok === false && row.last_sync_error ? (
              <span className="ml-2 text-xs text-red-400">{row.last_sync_error}</span>
            ) : null}
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
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
    <div className="space-y-8" data-testid="broker-connections-tab">
      <ArrConnectionCard title="Sonarr" arrType="sonarr" canOperate={canOperate} />
      <ArrConnectionCard title="Radarr" arrType="radarr" canOperate={canOperate} />

      <section className="mm-card mm-dash-card mm-fetcher-module-surface" data-testid="broker-connections-proxy">
        <h2 className="mm-card__title text-lg">Proxy API key</h2>
        <div className="mm-card__body mt-5 space-y-4 text-sm text-[var(--mm-text2)]">
          <p>
            Use this key to point Sonarr or Radarr directly at Broker as a single unified indexer. Copy the Torznab or
            Newznab URL into your *arr indexer settings.
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
