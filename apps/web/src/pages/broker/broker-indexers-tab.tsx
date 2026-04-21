import { useEffect, useId, useMemo, useState, type ReactNode } from "react";
import { PageLoading } from "../../components/shared/page-loading";
import { MmOnOffSwitch } from "../../components/ui/mm-on-off-switch";
import { BROKER_NATIVE_INDEXERS, type BrokerNativeCatalogEntry } from "../../lib/broker/broker-native-catalog";
import type { BrokerIndexer } from "../../lib/broker/broker-api";
import {
  useBrokerIndexersQuery,
  useBrokerManualSyncMutation,
  useCreateBrokerIndexerMutation,
  useDeleteBrokerIndexerMutation,
  useTestBrokerIndexerMutation,
  useUpdateBrokerIndexerMutation,
} from "../../lib/broker/broker-queries";
import { mmActionButtonClass } from "../../lib/ui/mm-control-roles";

const CATEGORY_OPTIONS: { id: number; label: string }[] = [
  { id: 5000, label: "5000 · TV" },
  { id: 2000, label: "2000 · Movies" },
  { id: 5070, label: "5070 · Anime" },
  { id: 8000, label: "8000 · Other" },
];

function slugifyPart(s: string): string {
  const x = s
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "_")
    .replace(/^_+|_+$/g, "");
  return x || "indexer";
}

function Pill({ children, tone }: { children: ReactNode; tone: "neutral" | "blue" | "purple" }) {
  const cls =
    tone === "blue"
      ? "border-sky-500/40 bg-sky-500/10 text-sky-200"
      : tone === "purple"
        ? "border-violet-500/40 bg-violet-500/10 text-violet-200"
        : "border-[var(--mm-border)] bg-black/15 text-[var(--mm-text2)]";
  return (
    <span className={`inline-flex rounded-full border px-2 py-0.5 text-[0.65rem] font-semibold uppercase tracking-wide ${cls}`}>
      {children}
    </span>
  );
}

function protocolLabel(p: string): string {
  const x = p.toLowerCase();
  if (x === "torrent") return "Torrent";
  if (x === "usenet") return "Usenet";
  return p;
}

function privacyLabel(p: string): string {
  const x = p.toLowerCase();
  if (x === "public") return "Public";
  if (x === "private") return "Private";
  return p;
}

function testDotTone(ix: BrokerIndexer): "ok" | "bad" | "warn" {
  if (ix.last_test_ok === true) return "ok";
  if (ix.last_test_ok === false) return "bad";
  return "warn";
}

function TestDot({ ix }: { ix: BrokerIndexer }) {
  const t = testDotTone(ix);
  const cls = t === "ok" ? "bg-emerald-500" : t === "bad" ? "bg-red-500" : "bg-amber-500";
  return <span title={ix.last_test_error ?? ""} className={`inline-block h-2 w-2 shrink-0 rounded-full ${cls}`} aria-hidden="true" />;
}

function nativeMeta(slug: string): BrokerNativeCatalogEntry | undefined {
  return BROKER_NATIVE_INDEXERS.find((e) => e.slug === slug);
}

function indexerShowsUrl(ix: BrokerIndexer): boolean {
  const k = ix.kind.toLowerCase();
  return k === "torznab" || k === "newznab";
}

function indexerShowsApiKey(ix: BrokerIndexer): boolean {
  const k = ix.kind.toLowerCase();
  if (k === "torznab" || k === "newznab") {
    return true;
  }
  const meta = nativeMeta(ix.slug);
  return Boolean(meta?.requiresApiKey);
}

function IndexerAccordionRow({
  ix,
  expanded,
  onToggle,
  canOperate,
}: {
  ix: BrokerIndexer;
  expanded: boolean;
  onToggle: () => void;
  canOperate: boolean;
}) {
  const update = useUpdateBrokerIndexerMutation();
  const del = useDeleteBrokerIndexerMutation();
  const test = useTestBrokerIndexerMutation();

  const baseId = useId();
  const [url, setUrl] = useState(ix.url);
  const [apiKey, setApiKey] = useState("");
  const [showKey, setShowKey] = useState(false);
  const [priority, setPriority] = useState(String(ix.priority));
  const [cats, setCats] = useState<number[]>(ix.categories ?? []);
  const [localErr, setLocalErr] = useState<string | null>(null);
  const [testing, setTesting] = useState(false);
  const [testHint, setTestHint] = useState<string | null>(null);

  useEffect(() => {
    if (!expanded) {
      return;
    }
    setUrl(ix.url);
    setApiKey("");
    setPriority(String(ix.priority));
    setCats(ix.categories ?? []);
    setLocalErr(null);
    setTestHint(null);
  }, [expanded, ix]);

  function toggleCat(id: number) {
    setCats((prev) => (prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]));
  }

  async function onSave() {
    setLocalErr(null);
    try {
      const p = Number.parseInt(priority, 10);
      if (Number.isNaN(p)) {
        throw new Error("Priority must be a number.");
      }
      const tagList = ix.tags ?? [];
      const payload: Parameters<typeof update.mutateAsync>[0]["data"] = {
        url: indexerShowsUrl(ix) ? url.trim() : undefined,
        priority: p,
        categories: cats,
        tags: tagList,
      };
      if (indexerShowsApiKey(ix) && apiKey.trim()) {
        payload.api_key = apiKey.trim();
      }
      await update.mutateAsync({ id: ix.id, data: payload });
      setApiKey("");
    } catch (e) {
      setLocalErr((e as Error).message);
    }
  }

  async function onDelete() {
    if (!window.confirm(`Delete indexer “${ix.name}”? This cannot be undone.`)) {
      return;
    }
    try {
      await del.mutateAsync(ix.id);
    } catch (e) {
      setLocalErr((e as Error).message);
    }
  }

  async function onTest() {
    setLocalErr(null);
    setTestHint(null);
    setTesting(true);
    try {
      await test.mutateAsync(ix.id);
      setTestHint("Test queued — refresh row for result.");
    } catch (e) {
      setLocalErr((e as Error).message);
    } finally {
      setTesting(false);
    }
  }

  async function onToggleEnabled(next: boolean) {
    setLocalErr(null);
    try {
      await update.mutateAsync({ id: ix.id, data: { enabled: next } });
    } catch (e) {
      setLocalErr((e as Error).message);
    }
  }

  const mask = "\u2022".repeat(10);

  return (
    <div className="rounded-lg border border-[var(--mm-border)] bg-[var(--mm-card-bg)] shadow-sm" data-testid={`broker-indexer-row-${ix.id}`}>
      <button
        type="button"
        className="flex w-full items-center gap-2 px-3 py-2.5 text-left sm:gap-3 sm:px-4"
        onClick={onToggle}
        aria-expanded={expanded}
      >
        <span className="min-w-0 flex-1 truncate text-sm font-semibold text-[var(--mm-text1)]">{ix.name}</span>
        <Pill tone="blue">{protocolLabel(ix.protocol)}</Pill>
        <Pill tone="purple">{privacyLabel(ix.privacy)}</Pill>
        <div
          className="shrink-0"
          onClick={(e) => e.stopPropagation()}
          onKeyDown={(e) => e.stopPropagation()}
        >
          <MmOnOffSwitch
            id={`${baseId}-en`}
            label="Enabled"
            layout="inline"
            enabled={ix.enabled}
            disabled={!canOperate || update.isPending}
            onChange={(v) => void onToggleEnabled(v)}
          />
        </div>
        <TestDot ix={ix} />
        <span className="shrink-0 tabular-nums text-xs text-[var(--mm-text2)]">{ix.priority}</span>
        <svg
          aria-hidden
          className={`h-4 w-4 shrink-0 text-[var(--mm-text3)] transition-transform ${expanded ? "rotate-180" : ""}`}
          viewBox="0 0 20 20"
          fill="currentColor"
        >
          <path d="M5.5 7.5 10 12l4.5-4.5H5.5z" />
        </svg>
      </button>
      {expanded ? (
        <div className="space-y-3 border-t border-[var(--mm-border)] bg-black/10 px-3 py-3 sm:px-4">
          {indexerShowsUrl(ix) ? (
            <input
              className="mm-input w-full font-mono text-sm"
              value={url}
              onChange={(e) => setUrl(e.target.value)}
              placeholder="URL"
              aria-label="Indexer URL"
            />
          ) : null}
          {indexerShowsApiKey(ix) ? (
            <div className="flex flex-wrap items-center gap-2">
              <input
                className="mm-input min-w-0 flex-1 font-mono text-sm"
                type={showKey ? "text" : "password"}
                placeholder={mask}
                value={apiKey}
                onChange={(e) => setApiKey(e.target.value)}
                autoComplete="off"
                aria-label="API key"
              />
              <button type="button" className={mmActionButtonClass({ variant: "secondary" })} onClick={() => setShowKey((s) => !s)}>
                {showKey ? "Hide" : "Show"}
              </button>
            </div>
          ) : null}
          <div className="flex flex-wrap items-center gap-3">
            <MmOnOffSwitch
              id={`${baseId}-en-expanded`}
              label="Enabled"
              layout="inline"
              enabled={ix.enabled}
              disabled={!canOperate || update.isPending}
              onChange={(v) => void onToggleEnabled(v)}
            />
            <label className="flex items-center gap-2 text-xs text-[var(--mm-text2)]">
              Priority
              <input
                className="mm-input w-16 tabular-nums"
                inputMode="numeric"
                value={priority}
                onChange={(e) => setPriority(e.target.value)}
              />
            </label>
          </div>
          <div className="flex flex-wrap gap-1.5">
            {CATEGORY_OPTIONS.map((c) => {
              const on = cats.includes(c.id);
              return (
                <button
                  key={c.id}
                  type="button"
                  aria-pressed={on}
                  onClick={() => toggleCat(c.id)}
                  className={[
                    "rounded-full border px-2.5 py-0.5 text-[0.7rem] font-medium transition-colors",
                    on
                      ? "border-[rgba(212,175,55,0.45)] bg-[var(--mm-accent-soft)] text-[var(--mm-text1)]"
                      : "border-[var(--mm-border)] bg-transparent text-[var(--mm-text2)] hover:bg-white/5",
                  ].join(" ")}
                >
                  {c.label}
                </button>
              );
            })}
          </div>
          <div className="flex flex-wrap gap-2">
            <button
              type="button"
              className={mmActionButtonClass({ variant: "secondary", disabled: !canOperate || testing })}
              disabled={!canOperate || testing}
              onClick={() => void onTest()}
            >
              {testing ? "Testing…" : "Test"}
            </button>
            <button
              type="button"
              className={mmActionButtonClass({ variant: "primary", disabled: !canOperate || update.isPending })}
              disabled={!canOperate || update.isPending}
              onClick={() => void onSave()}
            >
              {update.isPending ? "Saving…" : "Save"}
            </button>
            <button
              type="button"
              className={mmActionButtonClass({ variant: "secondary", disabled: !canOperate || del.isPending })}
              disabled={!canOperate || del.isPending}
              onClick={() => void onDelete()}
            >
              Delete
            </button>
          </div>
          {testHint ? <p className="text-xs text-[var(--mm-text3)]">{testHint}</p> : null}
          {localErr ? (
            <p className="text-sm text-red-400" role="alert">
              {localErr}
            </p>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}

function PendingCustomRow({
  protocol,
  canOperate,
  onCancel,
  onSave,
  busy,
}: {
  protocol: "torrent" | "usenet";
  canOperate: boolean;
  onCancel: () => void;
  onSave: (payload: {
    name: string;
    url: string;
    apiKey: string;
    priority: string;
    cats: number[];
    enabled: boolean;
  }) => Promise<void>;
  busy: boolean;
}) {
  const baseId = useId();
  const [name, setName] = useState("");
  const [url, setUrl] = useState("");
  const [apiKey, setApiKey] = useState("");
  const [showKey, setShowKey] = useState(false);
  const [priority, setPriority] = useState("25");
  const [cats, setCats] = useState<number[]>(protocol === "torrent" ? [5000, 2000] : [2000, 5000]);
  const [enabled, setEnabled] = useState(true);

  return (
    <div className="rounded-lg border border-[rgba(212,175,55,0.35)] bg-[var(--mm-card-bg)] shadow-sm">
      <div className="flex items-center justify-between gap-2 border-b border-[var(--mm-border)] px-3 py-2 sm:px-4">
        <span className="text-sm font-semibold text-[var(--mm-text1)]">New custom indexer</span>
        <button type="button" className={mmActionButtonClass({ variant: "secondary", disabled: busy })} disabled={busy} onClick={onCancel}>
          Cancel
        </button>
      </div>
      <div className="space-y-3 px-3 py-3 sm:px-4">
        <input className="mm-input w-full" value={name} onChange={(e) => setName(e.target.value)} placeholder="Name (required)" />
        <input className="mm-input w-full font-mono text-sm" value={url} onChange={(e) => setUrl(e.target.value)} placeholder="URL (required)" />
        <div className="flex flex-wrap gap-2">
          <input
            className="mm-input min-w-0 flex-1 font-mono text-sm"
            type={showKey ? "text" : "password"}
            placeholder={"API key (optional)"}
            value={apiKey}
            onChange={(e) => setApiKey(e.target.value)}
          />
          <button type="button" className={mmActionButtonClass({ variant: "secondary" })} onClick={() => setShowKey((s) => !s)}>
            {showKey ? "Hide" : "Show"}
          </button>
        </div>
        <div className="flex flex-wrap items-center gap-3">
          <MmOnOffSwitch id={`${baseId}-pen`} label="Enabled" layout="inline" enabled={enabled} disabled={busy} onChange={setEnabled} />
          <label className="flex items-center gap-2 text-xs text-[var(--mm-text2)]">
            Priority
            <input className="mm-input w-16 tabular-nums" value={priority} onChange={(e) => setPriority(e.target.value)} />
          </label>
        </div>
        <div className="flex flex-wrap gap-1.5">
          {CATEGORY_OPTIONS.map((c) => {
            const on = cats.includes(c.id);
            return (
              <button
                key={c.id}
                type="button"
                aria-pressed={on}
                onClick={() => setCats((prev) => (prev.includes(c.id) ? prev.filter((x) => x !== c.id) : [...prev, c.id]))}
                className={[
                  "rounded-full border px-2.5 py-0.5 text-[0.7rem] font-medium transition-colors",
                  on
                    ? "border-[rgba(212,175,55,0.45)] bg-[var(--mm-accent-soft)] text-[var(--mm-text1)]"
                    : "border-[var(--mm-border)] bg-transparent text-[var(--mm-text2)] hover:bg-white/5",
                ].join(" ")}
              >
                {c.label}
              </button>
            );
          })}
        </div>
        <button
          type="button"
          className={mmActionButtonClass({ variant: "primary", disabled: !canOperate || busy })}
          disabled={!canOperate || busy}
          onClick={() => void onSave({ name, url, apiKey, priority, cats, enabled })}
        >
          {busy ? "Saving…" : "Save"}
        </button>
      </div>
    </div>
  );
}

export function BrokerIndexersTab({ canOperate }: { canOperate: boolean }) {
  const q = useBrokerIndexersQuery();
  const syncSonarr = useBrokerManualSyncMutation("sonarr");
  const syncRadarr = useBrokerManualSyncMutation("radarr");
  const create = useCreateBrokerIndexerMutation();

  const [expandedId, setExpandedId] = useState<number | null>(null);
  const [catalogOpen, setCatalogOpen] = useState(false);
  const [catalogErr, setCatalogErr] = useState<string | null>(null);
  const [nativeFilter, setNativeFilter] = useState("");
  const [nativeKeyEntry, setNativeKeyEntry] = useState<BrokerNativeCatalogEntry | null>(null);
  const [nativeKeyValue, setNativeKeyValue] = useState("");
  const [pendingTorrent, setPendingTorrent] = useState(false);
  const [pendingUsenet, setPendingUsenet] = useState(false);

  const torrentRows = useMemo(() => (q.data ?? []).filter((i) => i.protocol === "torrent"), [q.data]);
  const usenetRows = useMemo(() => (q.data ?? []).filter((i) => i.protocol === "usenet"), [q.data]);

  const nativeTorrent = useMemo(() => BROKER_NATIVE_INDEXERS.filter((e) => e.protocol === "torrent"), []);
  const nativeUsenet = useMemo(() => BROKER_NATIVE_INDEXERS.filter((e) => e.protocol === "usenet"), []);

  const filteredNative = useMemo(() => {
    const f = nativeFilter.trim().toLowerCase();
    const match = (e: BrokerNativeCatalogEntry) => !f || e.name.toLowerCase().includes(f) || e.slug.toLowerCase().includes(f);
    return { torrent: nativeTorrent.filter(match), usenet: nativeUsenet.filter(match) };
  }, [nativeFilter, nativeTorrent, nativeUsenet]);

  function openCatalog() {
    setCatalogErr(null);
    setNativeFilter("");
    setNativeKeyEntry(null);
    setNativeKeyValue("");
    setCatalogOpen(true);
  }

  function closeCatalog() {
    setCatalogOpen(false);
    setCatalogErr(null);
    setNativeKeyEntry(null);
    setNativeKeyValue("");
  }

  async function createNativeIndexer(entry: BrokerNativeCatalogEntry, apiKey: string) {
    return create.mutateAsync({
      name: entry.name,
      slug: entry.slug,
      kind: entry.slug,
      protocol: entry.protocol,
      privacy: entry.privacy,
      url: "",
      api_key: apiKey.trim(),
      enabled: true,
      priority: 25,
      categories: entry.protocol === "torrent" ? [5000] : [2000, 5000],
      tags: [],
    });
  }

  function onCatalogRowClick(entry: BrokerNativeCatalogEntry) {
    setCatalogErr(null);
    if (entry.requiresApiKey) {
      setNativeKeyEntry(entry);
      setNativeKeyValue("");
      return;
    }
    void (async () => {
      try {
        const created = await createNativeIndexer(entry, "");
        closeCatalog();
        setExpandedId(created.id);
      } catch (e) {
        setCatalogErr((e as Error).message);
      }
    })();
  }

  async function confirmNativeWithKey() {
    if (!nativeKeyEntry) return;
    if (!nativeKeyValue.trim()) {
      setCatalogErr("API key is required for this indexer.");
      return;
    }
    setCatalogErr(null);
    try {
      const created = await createNativeIndexer(nativeKeyEntry, nativeKeyValue);
      closeCatalog();
      setExpandedId(created.id);
    } catch (e) {
      setCatalogErr((e as Error).message);
    }
  }

  async function savePendingTorrent(payload: {
    name: string;
    url: string;
    apiKey: string;
    priority: string;
    cats: number[];
    enabled: boolean;
  }) {
    const pr = Number.parseInt(payload.priority, 10);
    if (Number.isNaN(pr)) throw new Error("Priority must be a number.");
    const name = payload.name.trim();
    if (!name) throw new Error("Name is required.");
    if (!payload.url.trim()) throw new Error("URL is required.");
    const slug = `torznab__${slugifyPart(name)}`;
    const created = await create.mutateAsync({
      name,
      slug,
      kind: "torznab",
      protocol: "torrent",
      privacy: "public",
      url: payload.url.trim(),
      api_key: payload.apiKey.trim(),
      enabled: payload.enabled,
      priority: pr,
      categories: payload.cats,
      tags: [],
    });
    setPendingTorrent(false);
    setExpandedId(created.id);
  }

  async function savePendingUsenet(payload: {
    name: string;
    url: string;
    apiKey: string;
    priority: string;
    cats: number[];
    enabled: boolean;
  }) {
    const pr = Number.parseInt(payload.priority, 10);
    if (Number.isNaN(pr)) throw new Error("Priority must be a number.");
    const name = payload.name.trim();
    if (!name) throw new Error("Name is required.");
    if (!payload.url.trim()) throw new Error("URL is required.");
    const slug = `newznab__${slugifyPart(name)}`;
    const created = await create.mutateAsync({
      name,
      slug,
      kind: "newznab",
      protocol: "usenet",
      privacy: "public",
      url: payload.url.trim(),
      api_key: payload.apiKey.trim(),
      enabled: payload.enabled,
      priority: pr,
      categories: payload.cats,
      tags: [],
    });
    setPendingUsenet(false);
    setExpandedId(created.id);
  }

  if (q.isPending) {
    return <PageLoading />;
  }
  if (q.isError) {
    return <p className="text-sm text-red-400">{(q.error as Error).message}</p>;
  }

  return (
    <div className="mm-bubble-stack" data-testid="broker-indexers-tab">
      <div className="flex flex-col gap-3 sm:flex-row sm:flex-wrap sm:items-center sm:justify-between">
        <div className="flex flex-wrap items-center gap-2">
          <button
            type="button"
            className={mmActionButtonClass({ variant: "secondary", disabled: !canOperate || syncSonarr.isPending })}
            disabled={!canOperate || syncSonarr.isPending}
            onClick={() => void syncSonarr.mutateAsync().catch(() => {})}
          >
            {syncSonarr.isPending ? "Enqueuing…" : "Sync Sonarr"}
          </button>
          <button
            type="button"
            className={mmActionButtonClass({ variant: "secondary", disabled: !canOperate || syncRadarr.isPending })}
            disabled={!canOperate || syncRadarr.isPending}
            onClick={() => void syncRadarr.mutateAsync().catch(() => {})}
          >
            {syncRadarr.isPending ? "Enqueuing…" : "Sync Radarr"}
          </button>
        </div>
        <div className="flex flex-wrap items-center justify-end gap-2">
          <button
            type="button"
            className={mmActionButtonClass({ variant: "secondary", disabled: !canOperate })}
            disabled={!canOperate}
            onClick={() => {
              setExpandedId(null);
              setPendingUsenet(true);
              setPendingTorrent(false);
            }}
          >
            Add custom Newznab
          </button>
          <button
            type="button"
            className={mmActionButtonClass({ variant: "secondary", disabled: !canOperate })}
            disabled={!canOperate}
            onClick={() => {
              setExpandedId(null);
              setPendingTorrent(true);
              setPendingUsenet(false);
            }}
          >
            Add custom Torznab
          </button>
          <button type="button" className={mmActionButtonClass({ variant: "primary", disabled: !canOperate })} disabled={!canOperate} onClick={openCatalog}>
            Add indexer
          </button>
        </div>
      </div>

      <section
        className="overflow-hidden rounded-lg border border-[var(--mm-border)] bg-[var(--mm-card-bg)] shadow-sm"
        data-testid="broker-indexers-torrent-group"
      >
        <header className="border-b border-[var(--mm-border)] bg-black/10 px-4 py-3 sm:px-5">
          <p className="text-[0.7rem] font-semibold uppercase tracking-[0.12em] text-[var(--mm-text2)]">Torrent</p>
          <h2 className="mt-0.5 text-sm font-semibold text-[var(--mm-text1)]">Torrent indexers</h2>
        </header>
        <div className="divide-y divide-[var(--mm-border)] px-3 py-3 sm:px-4 sm:py-4">
          {pendingTorrent ? (
            <div className="pb-3">
              <PendingCustomRow
                protocol="torrent"
                canOperate={canOperate}
                busy={create.isPending}
                onCancel={() => setPendingTorrent(false)}
                onSave={async (p) => {
                  try {
                    await savePendingTorrent(p);
                  } catch (e) {
                    window.alert((e as Error).message);
                  }
                }}
              />
            </div>
          ) : null}
          <div className="space-y-2 pt-1">
            {torrentRows.map((ix) => (
              <IndexerAccordionRow
                key={ix.id}
                ix={ix}
                expanded={expandedId === ix.id}
                canOperate={canOperate}
                onToggle={() => setExpandedId((cur) => (cur === ix.id ? null : ix.id))}
              />
            ))}
            {torrentRows.length === 0 && !pendingTorrent ? (
              <p className="py-2 text-sm text-[var(--mm-text2)]">No torrent indexers yet.</p>
            ) : null}
          </div>
        </div>
      </section>

      <section
        className="overflow-hidden rounded-lg border border-[var(--mm-border)] bg-[var(--mm-card-bg)] shadow-sm"
        data-testid="broker-indexers-usenet-group"
      >
        <header className="border-b border-[var(--mm-border)] bg-black/10 px-4 py-3 sm:px-5">
          <p className="text-[0.7rem] font-semibold uppercase tracking-[0.12em] text-[var(--mm-text2)]">Usenet</p>
          <h2 className="mt-0.5 text-sm font-semibold text-[var(--mm-text1)]">Usenet indexers</h2>
        </header>
        <div className="divide-y divide-[var(--mm-border)] px-3 py-3 sm:px-4 sm:py-4">
          {pendingUsenet ? (
            <div className="pb-3">
              <PendingCustomRow
                protocol="usenet"
                canOperate={canOperate}
                busy={create.isPending}
                onCancel={() => setPendingUsenet(false)}
                onSave={async (p) => {
                  try {
                    await savePendingUsenet(p);
                  } catch (e) {
                    window.alert((e as Error).message);
                  }
                }}
              />
            </div>
          ) : null}
          <div className="space-y-2 pt-1">
            {usenetRows.map((ix) => (
              <IndexerAccordionRow
                key={ix.id}
                ix={ix}
                expanded={expandedId === ix.id}
                canOperate={canOperate}
                onToggle={() => setExpandedId((cur) => (cur === ix.id ? null : ix.id))}
              />
            ))}
            {usenetRows.length === 0 && !pendingUsenet ? (
              <p className="py-2 text-sm text-[var(--mm-text2)]">No Usenet indexers yet.</p>
            ) : null}
          </div>
        </div>
      </section>

      {catalogOpen ? (
        <div className="fixed inset-0 z-50 flex justify-end bg-black/50" role="presentation">
          <button type="button" className="absolute inset-0 cursor-default" aria-label="Close catalog" onClick={closeCatalog} />
          <aside
            className="relative z-10 flex h-full w-full max-w-xl flex-col border-l border-[var(--mm-border)] bg-[var(--mm-card-bg)] shadow-2xl"
            role="dialog"
            aria-modal="true"
            aria-label="Add indexer from catalog"
          >
            <div className="flex items-center justify-between gap-3 border-b border-[var(--mm-border)] px-4 py-3">
              <h2 className="text-base font-semibold text-[var(--mm-text1)]">Add indexer</h2>
              <button type="button" className={mmActionButtonClass({ variant: "secondary" })} onClick={closeCatalog}>
                Back
              </button>
            </div>
            <div className="min-h-0 flex-1 overflow-y-auto px-4 py-4">
              <input
                className="mm-input w-full"
                value={nativeFilter}
                onChange={(e) => setNativeFilter(e.target.value)}
                placeholder="Search catalog…"
                aria-label="Search catalog"
              />
              {catalogErr ? (
                <p className="mt-3 text-sm text-red-400" role="alert">
                  {catalogErr}
                </p>
              ) : null}
              {nativeKeyEntry ? (
                <div className="mt-4 rounded-md border border-[var(--mm-border)] bg-black/15 p-3">
                  <p className="text-sm text-[var(--mm-text2)]">
                    <span className="font-medium text-[var(--mm-text1)]">{nativeKeyEntry.name}</span> needs an API key.
                  </p>
                  <input
                    className="mm-input mt-2 w-full font-mono text-sm"
                    value={nativeKeyValue}
                    onChange={(e) => setNativeKeyValue(e.target.value)}
                    autoComplete="off"
                    placeholder="API key"
                    aria-label="API key for indexer"
                  />
                  <div className="mt-2 flex flex-wrap gap-2">
                    <button type="button" className={mmActionButtonClass({ variant: "primary" })} onClick={() => void confirmNativeWithKey()}>
                      Add indexer
                    </button>
                    <button type="button" className={mmActionButtonClass({ variant: "secondary" })} onClick={() => setNativeKeyEntry(null)}>
                      Cancel
                    </button>
                  </div>
                </div>
              ) : null}
              <div className="mt-5 space-y-5">
                <div>
                  <p className="text-xs font-semibold uppercase tracking-wide text-[var(--mm-text3)]">Torrent</p>
                  <ul className="mt-2 divide-y divide-[var(--mm-border)] rounded-md border border-[var(--mm-border)] bg-black/10">
                    {filteredNative.torrent.map((e) => (
                      <li key={e.slug}>
                        <button
                          type="button"
                          className="flex w-full items-center gap-2 px-3 py-2.5 text-left text-sm hover:bg-white/[0.04]"
                          onClick={() => onCatalogRowClick(e)}
                        >
                          <span className="min-w-0 flex-1 font-medium text-[var(--mm-text1)]">{e.name}</span>
                          <Pill tone="purple">{privacyLabel(e.privacy)}</Pill>
                          {e.requiresApiKey ? (
                            <span className="shrink-0 text-[0.65rem] text-[var(--mm-text3)]">Key required</span>
                          ) : null}
                        </button>
                      </li>
                    ))}
                  </ul>
                </div>
                <div>
                  <p className="text-xs font-semibold uppercase tracking-wide text-[var(--mm-text3)]">Usenet</p>
                  <ul className="mt-2 divide-y divide-[var(--mm-border)] rounded-md border border-[var(--mm-border)] bg-black/10">
                    {filteredNative.usenet.map((e) => (
                      <li key={e.slug}>
                        <button
                          type="button"
                          className="flex w-full items-center gap-2 px-3 py-2.5 text-left text-sm hover:bg-white/[0.04]"
                          onClick={() => onCatalogRowClick(e)}
                        >
                          <span className="min-w-0 flex-1 font-medium text-[var(--mm-text1)]">{e.name}</span>
                          <Pill tone="purple">{privacyLabel(e.privacy)}</Pill>
                          {e.requiresApiKey ? (
                            <span className="shrink-0 text-[0.65rem] text-[var(--mm-text3)]">Key required</span>
                          ) : null}
                        </button>
                      </li>
                    ))}
                  </ul>
                </div>
              </div>
            </div>
          </aside>
        </div>
      ) : null}
    </div>
  );
}
