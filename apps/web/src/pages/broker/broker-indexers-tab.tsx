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
  return <span className={`inline-flex rounded-full border px-2 py-0.5 text-[0.65rem] font-semibold uppercase tracking-wide ${cls}`}>{children}</span>;
}

function testDotTone(ix: BrokerIndexer): "ok" | "bad" | "muted" {
  if (ix.last_test_ok === true) {
    return "ok";
  }
  if (ix.last_test_ok === false) {
    return "bad";
  }
  return "muted";
}

function TestDot({ ix }: { ix: BrokerIndexer }) {
  const t = testDotTone(ix);
  const cls = t === "ok" ? "bg-emerald-500" : t === "bad" ? "bg-red-500" : "bg-[var(--mm-text3)]";
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

type AddWizardMode = "native" | "torznab" | "newznab" | null;

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
  const [tags, setTags] = useState((ix.tags ?? []).join(", "));
  const [localErr, setLocalErr] = useState<string | null>(null);

  useEffect(() => {
    if (!expanded) {
      return;
    }
    setUrl(ix.url);
    setApiKey("");
    setPriority(String(ix.priority));
    setCats(ix.categories ?? []);
    setTags((ix.tags ?? []).join(", "));
    setLocalErr(null);
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
      const tagList = tags
        .split(",")
        .map((s) => s.trim())
        .filter(Boolean);
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
    try {
      await test.mutateAsync(ix.id);
    } catch (e) {
      setLocalErr((e as Error).message);
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
    <div
      className="rounded-lg border border-[var(--mm-border)] bg-[var(--mm-card-bg)] shadow-sm"
      data-testid={`broker-indexer-row-${ix.id}`}
    >
      <button
        type="button"
        className="flex w-full items-center gap-3 px-4 py-3 text-left sm:px-5"
        onClick={onToggle}
        aria-expanded={expanded}
      >
        <span className="min-w-0 flex-1 font-medium text-[var(--mm-text1)]">{ix.name}</span>
        <Pill tone="neutral">{ix.kind}</Pill>
        <Pill tone="blue">{ix.protocol}</Pill>
        <Pill tone="purple">{ix.privacy}</Pill>
        <span className="tabular-nums text-sm text-[var(--mm-text2)]" title="Priority">
          {ix.priority}
        </span>
        <TestDot ix={ix} />
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
      </button>
      {expanded ? (
        <div className="space-y-4 border-t border-[var(--mm-border)] px-4 py-4 sm:px-5">
          {indexerShowsUrl(ix) ? (
            <label className="block">
              <span className="text-sm font-medium text-[var(--mm-text)]">URL</span>
              <input className="mm-input mt-1 w-full max-w-3xl" value={url} onChange={(e) => setUrl(e.target.value)} />
            </label>
          ) : null}
          {indexerShowsApiKey(ix) ? (
            <div>
              <span className="text-sm font-medium text-[var(--mm-text)]">API key</span>
              <div className="mt-1 flex max-w-3xl flex-wrap gap-2">
                <input
                  className="mm-input min-w-0 flex-1 font-mono text-sm"
                  type={showKey ? "text" : "password"}
                  placeholder={mask}
                  value={apiKey}
                  onChange={(e) => setApiKey(e.target.value)}
                  autoComplete="off"
                />
                <button
                  type="button"
                  className={mmActionButtonClass({ variant: "secondary" })}
                  onClick={() => setShowKey((s) => !s)}
                >
                  {showKey ? "Hide" : "Show"}
                </button>
              </div>
              <p className="mt-1 text-xs text-[var(--mm-text3)]">Leave blank to keep the saved key.</p>
            </div>
          ) : null}
          <label className="block max-w-xs">
            <span className="text-sm font-medium text-[var(--mm-text)]">Priority</span>
            <input
              className="mm-input mt-1 w-full tabular-nums"
              inputMode="numeric"
              value={priority}
              onChange={(e) => setPriority(e.target.value)}
            />
          </label>
          <fieldset>
            <legend className="text-sm font-medium text-[var(--mm-text)]">Categories</legend>
            <div className="mt-2 flex flex-wrap gap-3">
              {CATEGORY_OPTIONS.map((c) => (
                <label key={c.id} className="flex items-center gap-2 text-sm text-[var(--mm-text2)]">
                  <input type="checkbox" checked={cats.includes(c.id)} onChange={() => toggleCat(c.id)} />
                  {c.label}
                </label>
              ))}
            </div>
          </fieldset>
          <label className="block max-w-3xl">
            <span className="text-sm font-medium text-[var(--mm-text)]">Tags</span>
            <input className="mm-input mt-1 w-full" value={tags} onChange={(e) => setTags(e.target.value)} placeholder="comma, separated" />
          </label>
          <div className="flex flex-wrap gap-2">
            <button
              type="button"
              className={mmActionButtonClass({ variant: "secondary", disabled: !canOperate || test.isPending })}
              disabled={!canOperate || test.isPending}
              onClick={() => void onTest()}
            >
              {test.isPending ? "Testing…" : "Test"}
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
          {ix.last_tested_at ? (
            <p className="text-xs text-[var(--mm-text3)]">
              Last test: {ix.last_test_ok === true ? "OK" : ix.last_test_ok === false ? "Failed" : "—"}
              {ix.last_test_error ? ` — ${ix.last_test_error}` : ""}
            </p>
          ) : null}
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

export function BrokerIndexersTab({ canOperate }: { canOperate: boolean }) {
  const q = useBrokerIndexersQuery();
  const syncSonarr = useBrokerManualSyncMutation("sonarr");
  const syncRadarr = useBrokerManualSyncMutation("radarr");
  const create = useCreateBrokerIndexerMutation();

  const [expandedId, setExpandedId] = useState<number | null>(null);
  const [modalOpen, setModalOpen] = useState(false);
  /** 1 = pick kind, 2 = native catalog list, 3 = configure */
  const [step, setStep] = useState<1 | 2 | 3>(1);
  const [mode, setMode] = useState<AddWizardMode>(null);
  const [nativeFilter, setNativeFilter] = useState("");
  const [nativePick, setNativePick] = useState<BrokerNativeCatalogEntry | null>(null);

  const [gName, setGName] = useState("");
  const [gUrl, setGUrl] = useState("");
  const [gKey, setGKey] = useState("");
  const [gShowKey, setGShowKey] = useState(false);
  const [gPriority, setGPriority] = useState("25");
  const [gCats, setGCats] = useState<number[]>([5000, 2000]);
  const [gEnabled, setGEnabled] = useState(true);
  const [wizardErr, setWizardErr] = useState<string | null>(null);

  const torrentRows = useMemo(
    () => (q.data ?? []).filter((i) => i.protocol === "torrent"),
    [q.data],
  );
  const usenetRows = useMemo(
    () => (q.data ?? []).filter((i) => i.protocol === "usenet"),
    [q.data],
  );

  const nativeTorrent = useMemo(
    () => BROKER_NATIVE_INDEXERS.filter((e) => e.protocol === "torrent"),
    [],
  );
  const nativeUsenet = useMemo(
    () => BROKER_NATIVE_INDEXERS.filter((e) => e.protocol === "usenet"),
    [],
  );

  const filteredNative = useMemo(() => {
    const f = nativeFilter.trim().toLowerCase();
    const match = (e: BrokerNativeCatalogEntry) =>
      !f || e.name.toLowerCase().includes(f) || e.slug.toLowerCase().includes(f);
    return {
      torrent: nativeTorrent.filter(match),
      usenet: nativeUsenet.filter(match),
    };
  }, [nativeFilter, nativeTorrent, nativeUsenet]);

  function openModal() {
    setModalOpen(true);
    setStep(1);
    setMode(null);
    setNativePick(null);
    setNativeFilter("");
    setGName("");
    setGUrl("");
    setGKey("");
    setGPriority("25");
    setGCats([5000, 2000]);
    setGEnabled(true);
    setWizardErr(null);
  }

  function closeModal() {
    setModalOpen(false);
  }

  function chooseMode(m: AddWizardMode) {
    setWizardErr(null);
    if (m === "native") {
      setMode("native");
      setNativePick(null);
      setStep(2);
      return;
    }
    setMode(m);
    setStep(3);
    setGName("");
    setGUrl("");
    setGKey("");
    if (m === "torznab") {
      setGCats([5000, 2000]);
    } else if (m === "newznab") {
      setGCats([2000, 5000]);
    }
  }

  function chooseNative(entry: BrokerNativeCatalogEntry) {
    setMode("native");
    setNativePick(entry);
    setStep(3);
    setGName(entry.name);
    setGKey("");
    setGPriority("25");
    setGCats(entry.protocol === "torrent" ? [5000] : [2000, 5000]);
    setGEnabled(true);
    setWizardErr(null);
  }

  async function onCreateSave() {
    setWizardErr(null);
    try {
      const pr = Number.parseInt(gPriority, 10);
      if (Number.isNaN(pr)) {
        throw new Error("Priority must be a number.");
      }
      if (mode === "native" && nativePick) {
        if (nativePick.requiresApiKey && !gKey.trim()) {
          throw new Error("API key is required for this indexer.");
        }
        await create.mutateAsync({
          name: gName.trim() || nativePick.name,
          slug: nativePick.slug,
          kind: nativePick.slug,
          protocol: nativePick.protocol,
          privacy: nativePick.privacy,
          url: "",
          api_key: nativePick.requiresApiKey ? gKey.trim() : "",
          enabled: gEnabled,
          priority: pr,
          categories: gCats,
          tags: [],
        });
      } else if (mode === "torznab") {
        const name = gName.trim();
        if (!name) {
          throw new Error("Name is required.");
        }
        if (!gUrl.trim()) {
          throw new Error("URL is required for Torznab.");
        }
        const slug = `torznab__${slugifyPart(name)}`;
        await create.mutateAsync({
          name,
          slug,
          kind: "torznab",
          protocol: "torrent",
          privacy: "public",
          url: gUrl.trim(),
          api_key: gKey.trim(),
          enabled: gEnabled,
          priority: pr,
          categories: gCats,
          tags: [],
        });
      } else if (mode === "newznab") {
        const name = gName.trim();
        if (!name) {
          throw new Error("Name is required.");
        }
        if (!gUrl.trim()) {
          throw new Error("URL is required for Newznab.");
        }
        const slug = `newznab__${slugifyPart(name)}`;
        await create.mutateAsync({
          name,
          slug,
          kind: "newznab",
          protocol: "usenet",
          privacy: "public",
          url: gUrl.trim(),
          api_key: gKey.trim(),
          enabled: gEnabled,
          priority: pr,
          categories: gCats,
          tags: [],
        });
      }
      closeModal();
    } catch (e) {
      setWizardErr((e as Error).message);
    }
  }

  function toggleWizardCat(id: number) {
    setGCats((prev) => (prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]));
  }

  if (q.isPending) {
    return <PageLoading />;
  }
  if (q.isError) {
    return <p className="text-sm text-red-400">{(q.error as Error).message}</p>;
  }

  return (
    <div className="space-y-6" data-testid="broker-indexers-tab">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            className={mmActionButtonClass({ variant: "secondary", disabled: !canOperate || syncSonarr.isPending })}
            disabled={!canOperate || syncSonarr.isPending}
            onClick={() => void syncSonarr.mutateAsync().catch(() => {})}
          >
            {syncSonarr.isPending ? "Enqueuing…" : "Sync to Sonarr"}
          </button>
          <button
            type="button"
            className={mmActionButtonClass({ variant: "secondary", disabled: !canOperate || syncRadarr.isPending })}
            disabled={!canOperate || syncRadarr.isPending}
            onClick={() => void syncRadarr.mutateAsync().catch(() => {})}
          >
            {syncRadarr.isPending ? "Enqueuing…" : "Sync to Radarr"}
          </button>
        </div>
        <button
          type="button"
          className={mmActionButtonClass({ variant: "primary", disabled: !canOperate })}
          disabled={!canOperate}
          onClick={openModal}
        >
          Add indexer
        </button>
      </div>

      <section data-testid="broker-indexers-torrent-group">
        <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-[var(--mm-text3)]">Torrent</h2>
        <div className="space-y-3">
          {torrentRows.map((ix) => (
            <IndexerAccordionRow
              key={ix.id}
              ix={ix}
              expanded={expandedId === ix.id}
              canOperate={canOperate}
              onToggle={() => setExpandedId((cur) => (cur === ix.id ? null : ix.id))}
            />
          ))}
          {torrentRows.length === 0 ? <p className="text-sm text-[var(--mm-text2)]">No torrent indexers yet.</p> : null}
        </div>
      </section>

      <section data-testid="broker-indexers-usenet-group">
        <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-[var(--mm-text3)]">Usenet</h2>
        <div className="space-y-3">
          {usenetRows.map((ix) => (
            <IndexerAccordionRow
              key={ix.id}
              ix={ix}
              expanded={expandedId === ix.id}
              canOperate={canOperate}
              onToggle={() => setExpandedId((cur) => (cur === ix.id ? null : ix.id))}
            />
          ))}
          {usenetRows.length === 0 ? <p className="text-sm text-[var(--mm-text2)]">No Usenet indexers yet.</p> : null}
        </div>
      </section>

      {modalOpen ? (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4" role="presentation">
          <div
            role="dialog"
            aria-modal="true"
            className="max-h-[90vh] w-full max-w-2xl overflow-y-auto rounded-lg border border-[var(--mm-border)] bg-[var(--mm-card-bg)] p-5 shadow-xl"
          >
            <div className="flex items-start justify-between gap-3">
              <h2 className="text-lg font-semibold text-[var(--mm-text)]">Add indexer</h2>
              <button type="button" className={mmActionButtonClass({ variant: "secondary" })} onClick={closeModal}>
                Close
              </button>
            </div>

            {step === 1 ? (
              <div className="mt-5 space-y-3">
                <p className="text-sm text-[var(--mm-text2)]">Choose how to add this indexer.</p>
                <button type="button" className={mmActionButtonClass({ variant: "secondary" })} onClick={() => chooseMode("native")}>
                  Native indexer…
                </button>
                <button type="button" className={mmActionButtonClass({ variant: "secondary" })} onClick={() => chooseMode("torznab")}>
                  Torznab (custom URL)
                </button>
                <button type="button" className={mmActionButtonClass({ variant: "secondary" })} onClick={() => chooseMode("newznab")}>
                  Newznab (custom URL)
                </button>
              </div>
            ) : step === 2 && mode === "native" && !nativePick ? (
              <div className="mt-5 space-y-4">
                <label className="block">
                  <span className="text-sm font-medium text-[var(--mm-text)]">Search native indexers</span>
                  <input className="mm-input mt-1 w-full" value={nativeFilter} onChange={(e) => setNativeFilter(e.target.value)} />
                </label>
                <div>
                  <p className="text-xs font-semibold uppercase text-[var(--mm-text3)]">Torrent</p>
                  <ul className="mt-2 max-h-48 space-y-1 overflow-y-auto rounded border border-[var(--mm-border)] p-2">
                    {filteredNative.torrent.map((e) => (
                      <li key={e.slug}>
                        <button type="button" className="w-full rounded px-2 py-1.5 text-left text-sm hover:bg-white/5" onClick={() => chooseNative(e)}>
                          <span className="font-medium text-[var(--mm-text1)]">{e.name}</span>{" "}
                          <Pill tone="blue">torrent</Pill> <Pill tone="purple">{e.privacy}</Pill>
                        </button>
                      </li>
                    ))}
                  </ul>
                </div>
                <div>
                  <p className="text-xs font-semibold uppercase text-[var(--mm-text3)]">Usenet</p>
                  <ul className="mt-2 max-h-48 space-y-1 overflow-y-auto rounded border border-[var(--mm-border)] p-2">
                    {filteredNative.usenet.map((e) => (
                      <li key={e.slug}>
                        <button type="button" className="w-full rounded px-2 py-1.5 text-left text-sm hover:bg-white/5" onClick={() => chooseNative(e)}>
                          <span className="font-medium text-[var(--mm-text1)]">{e.name}</span>{" "}
                          <Pill tone="blue">usenet</Pill> <Pill tone="purple">{e.privacy}</Pill>
                        </button>
                      </li>
                    ))}
                  </ul>
                </div>
                <button type="button" className={mmActionButtonClass({ variant: "secondary" })} onClick={() => setStep(1)}>
                  Back
                </button>
              </div>
            ) : step === 3 ? (
              <div className="mt-5 space-y-4">
                {mode === "native" && nativePick ? (
                  <div>
                    <p className="text-sm text-[var(--mm-text2)]">
                      <span className="font-medium text-[var(--mm-text1)]">{nativePick.slug}</span> ·{" "}
                      <Pill tone="blue">{nativePick.protocol}</Pill> <Pill tone="purple">{nativePick.privacy}</Pill>
                    </p>
                    <label className="mt-3 block">
                      <span className="text-sm font-medium text-[var(--mm-text)]">Name</span>
                      <input className="mm-input mt-1 w-full" value={gName} onChange={(e) => setGName(e.target.value)} />
                    </label>
                  </div>
                ) : null}
                {(mode === "torznab" || mode === "newznab") && (
                  <label className="block">
                    <span className="text-sm font-medium text-[var(--mm-text)]">Name</span>
                    <input className="mm-input mt-1 w-full" value={gName} onChange={(e) => setGName(e.target.value)} />
                  </label>
                )}
                {(mode === "torznab" || mode === "newznab") && (
                  <label className="block">
                    <span className="text-sm font-medium text-[var(--mm-text)]">URL</span>
                    <input className="mm-input mt-1 w-full font-mono text-sm" value={gUrl} onChange={(e) => setGUrl(e.target.value)} />
                  </label>
                )}
                {mode === "native" && nativePick?.requiresApiKey ? (
                  <label className="block">
                    <span className="text-sm font-medium text-[var(--mm-text)]">API key</span>
                    <input className="mm-input mt-1 w-full font-mono text-sm" value={gKey} onChange={(e) => setGKey(e.target.value)} />
                  </label>
                ) : null}
                {(mode === "torznab" || mode === "newznab") && (
                  <div>
                    <span className="text-sm font-medium text-[var(--mm-text)]">API key</span>
                    <div className="mt-1 flex flex-wrap gap-2">
                      <input
                        className="mm-input min-w-0 flex-1 font-mono text-sm"
                        type={gShowKey ? "text" : "password"}
                        value={gKey}
                        onChange={(e) => setGKey(e.target.value)}
                      />
                      <button type="button" className={mmActionButtonClass({ variant: "secondary" })} onClick={() => setGShowKey((s) => !s)}>
                        {gShowKey ? "Hide" : "Show"}
                      </button>
                    </div>
                  </div>
                )}
                <label className="block max-w-xs">
                  <span className="text-sm font-medium text-[var(--mm-text)]">Priority</span>
                  <input className="mm-input mt-1 w-full" value={gPriority} onChange={(e) => setGPriority(e.target.value)} />
                </label>
                <fieldset>
                  <legend className="text-sm font-medium text-[var(--mm-text)]">Categories</legend>
                  <div className="mt-2 flex flex-wrap gap-3">
                    {CATEGORY_OPTIONS.map((c) => (
                      <label key={c.id} className="flex items-center gap-2 text-sm text-[var(--mm-text2)]">
                        <input type="checkbox" checked={gCats.includes(c.id)} onChange={() => toggleWizardCat(c.id)} />
                        {c.label}
                      </label>
                    ))}
                  </div>
                </fieldset>
                <MmOnOffSwitch id="wiz-en" label="Enabled" enabled={gEnabled} disabled={false} onChange={setGEnabled} />
                {wizardErr ? (
                  <p className="text-sm text-red-400" role="alert">
                    {wizardErr}
                  </p>
                ) : null}
                <div className="flex flex-wrap gap-2">
                  <button
                    type="button"
                    className={mmActionButtonClass({ variant: "secondary" })}
                    onClick={() => {
                      if (mode === "native" && nativePick) {
                        setNativePick(null);
                        setStep(2);
                        return;
                      }
                      setStep(1);
                    }}
                  >
                    Back
                  </button>
                  <button
                    type="button"
                    className={mmActionButtonClass({ variant: "primary", disabled: create.isPending })}
                    disabled={create.isPending}
                    onClick={() => void onCreateSave()}
                  >
                    {create.isPending ? "Saving…" : "Save indexer"}
                  </button>
                </div>
              </div>
            ) : null}
          </div>
        </div>
      ) : null}
    </div>
  );
}
