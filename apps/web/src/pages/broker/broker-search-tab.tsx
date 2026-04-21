import { useId, useMemo, useState } from "react";
import { MmMultiListboxPicker } from "../../components/ui/mm-multi-listbox-picker";
import type { BrokerIndexer, BrokerResult } from "../../lib/broker/broker-api";
import { useBrokerIndexersQuery, useBrokerSearchMutation } from "../../lib/broker/broker-queries";
import { mmActionButtonClass } from "../../lib/ui/mm-control-roles";

const TYPE_VALUES = ["all", "tv", "movie"] as const;

function formatBytes(n: number): string {
  const units = ["B", "KB", "MB", "GB", "TB"];
  let v = Math.max(0, n);
  let i = 0;
  while (v >= 1024 && i < units.length - 1) {
    v /= 1024;
    i += 1;
  }
  const rounded = i === 0 ? String(Math.round(v)) : v >= 10 ? Math.round(v).toString() : v.toFixed(1);
  return `${rounded} ${units[i]}`;
}

function relativeAge(iso: string | null): string {
  if (!iso) {
    return "—";
  }
  const t = new Date(iso).getTime();
  if (Number.isNaN(t)) {
    return "—";
  }
  const diffSec = Math.round((t - Date.now()) / 1000);
  const rtf = new Intl.RelativeTimeFormat(undefined, { numeric: "auto" });
  const divisions: { unit: Intl.RelativeTimeFormatUnit; n: number }[] = [
    { unit: "year", n: 60 * 60 * 24 * 365 },
    { unit: "month", n: 60 * 60 * 24 * 30 },
    { unit: "week", n: 60 * 60 * 24 * 7 },
    { unit: "day", n: 60 * 60 * 24 },
    { unit: "hour", n: 60 * 60 },
    { unit: "minute", n: 60 },
    { unit: "second", n: 1 },
  ];
  const abs = Math.abs(diffSec);
  for (const { unit, n } of divisions) {
    if (abs >= n || unit === "second") {
      return rtf.format(Math.round(diffSec / n), unit);
    }
  }
  return rtf.format(0, "second");
}

function isTvHeavy(r: BrokerResult): boolean {
  const cats = r.categories ?? [];
  if (cats.some((c) => c === 5000 || c === 5030 || c === 5040)) {
    return true;
  }
  if (cats.includes(2000)) {
    return false;
  }
  return r.protocol === "torrent";
}

function sortResultsForDisplay(mediaType: string, rows: BrokerResult[]): BrokerResult[] {
  if (mediaType !== "all") {
    return rows;
  }
  return [...rows].sort((a, b) => {
    const atv = isTvHeavy(a) ? 0 : 1;
    const btv = isTvHeavy(b) ? 0 : 1;
    return atv - btv;
  });
}

function protocolBadge(p: string): string {
  const x = p.toLowerCase();
  if (x === "torrent") return "Torrent";
  if (x === "usenet") return "Usenet";
  return p;
}

function privacyBadgeLabel(privacy: string): string {
  const x = privacy.toLowerCase();
  if (x === "private") return "Private";
  return "Public";
}

function ResultBadges({ r, indexerName, privacy }: { r: BrokerResult; indexerName: string; privacy: string }) {
  return (
    <div className="flex flex-wrap gap-1.5">
      <span className="rounded-full border border-[var(--mm-border)] bg-black/20 px-2 py-0.5 text-[0.65rem] font-semibold uppercase tracking-wide text-[var(--mm-text2)]">
        {protocolBadge(r.protocol)}
      </span>
      <span className="max-w-[10rem] truncate rounded-full border border-sky-500/30 bg-sky-500/10 px-2 py-0.5 text-[0.65rem] font-medium text-sky-200" title={indexerName}>
        {indexerName}
      </span>
      <span className="rounded-full border border-violet-500/30 bg-violet-500/10 px-2 py-0.5 text-[0.65rem] font-medium text-violet-200">{privacyBadgeLabel(privacy)}</span>
    </div>
  );
}

function ResultCard({
  r,
  indexerName,
  privacy,
}: {
  r: BrokerResult;
  indexerName: string;
  privacy: string;
}) {
  const [expanded, setExpanded] = useState(false);
  const [copyOk, setCopyOk] = useState(false);

  async function copyLink() {
    try {
      await navigator.clipboard.writeText(r.url);
      setCopyOk(true);
      window.setTimeout(() => setCopyOk(false), 2000);
    } catch {
      /* ignore */
    }
  }

  const seeders = r.seeders ?? null;
  const seedClass = seeders != null && seeders > 0 ? "text-emerald-500" : "text-[var(--mm-text2)]";

  return (
    <article className="flex flex-col rounded-lg border border-[var(--mm-border)] bg-[var(--mm-card-bg)] p-3 shadow-sm sm:p-4">
      <button
        type="button"
        className="text-left"
        onClick={() => setExpanded((x) => !x)}
        title={r.title}
      >
        <h3 className={`text-sm font-semibold text-[var(--mm-text1)] ${expanded ? "" : "line-clamp-2"}`}>{r.title}</h3>
      </button>
      <div className="mt-2">
        <ResultBadges r={r} indexerName={indexerName} privacy={privacy} />
      </div>
      <div className={`mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs tabular-nums text-[var(--mm-text2)]`}>
        <span className={seedClass}>Seeders {seeders ?? "—"}</span>
        <span>Size {formatBytes(r.size)}</span>
        <span>Age {relativeAge(r.published_at)}</span>
      </div>
      <div className="mt-3 flex flex-wrap gap-2">
        {r.magnet ? (
          <a className={mmActionButtonClass({ variant: "secondary" })} href={r.magnet} rel="noreferrer">
            Magnet
          </a>
        ) : null}
        <a className={mmActionButtonClass({ variant: "secondary" })} href={r.url} target="_blank" rel="noreferrer" download>
          Download
        </a>
        <button type="button" className={mmActionButtonClass({ variant: "secondary" })} onClick={() => void copyLink()}>
          {copyOk ? "Copied" : "Copy link"}
        </button>
      </div>
    </article>
  );
}

function SearchResultsSkeleton() {
  return (
    <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
      {Array.from({ length: 6 }).map((_, i) => (
        <div
          key={i}
          className="animate-pulse rounded-lg border border-[var(--mm-border)] bg-[var(--mm-card-bg)] p-4"
          aria-hidden
        >
          <div className="h-4 w-full max-w-[75%] rounded bg-[var(--mm-border)]" />
          <div className="mt-3 h-3 w-1/2 rounded bg-[var(--mm-border)]" />
          <div className="mt-4 h-3 w-full rounded bg-[var(--mm-border)]" />
          <div className="mt-2 h-8 w-24 rounded bg-[var(--mm-border)]" />
        </div>
      ))}
    </div>
  );
}

export function BrokerSearchTab() {
  const ix = useBrokerIndexersQuery();
  const search = useBrokerSearchMutation();
  const ixLabel = useId();

  const [q, setQ] = useState("");
  const [mediaType, setMediaType] = useState<(typeof TYPE_VALUES)[number]>("all");
  const [indexerValues, setIndexerValues] = useState<string[]>([]);

  const enabled = useMemo(() => (ix.data ?? []).filter((i) => i.enabled), [ix.data]);
  const indexerOptions = useMemo(() => enabled.map((i) => ({ value: String(i.id), label: i.name })), [enabled]);
  const slugToName = useMemo(() => {
    const m = new Map<string, string>();
    for (const i of ix.data ?? []) {
      m.set(i.slug, i.name);
    }
    return m;
  }, [ix.data]);

  const slugToIndexer = useMemo(() => {
    const m = new Map<string, BrokerIndexer>();
    for (const i of ix.data ?? []) {
      m.set(i.slug, i);
    }
    return m;
  }, [ix.data]);

  const enabledIds = useMemo(() => new Set(enabled.map((i) => String(i.id))), [enabled]);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!q.trim()) {
      return;
    }
    let indexersParam: string | undefined;
    if (indexerValues.length > 0) {
      const subset = indexerValues.filter((id) => enabledIds.has(id));
      if (subset.length > 0 && subset.length < enabled.length) {
        indexersParam = subset.join(",");
      }
    }
    await search.mutateAsync({
      q: q.trim(),
      type: mediaType === "all" ? undefined : mediaType,
      indexers: indexersParam,
      limit: 50,
    });
  }

  const rows = sortResultsForDisplay(mediaType, search.data ?? []);
  const enabledCount = enabled.length;

  return (
    <div className="mm-bubble-stack" data-testid="broker-search-tab">
      <section className="mm-card mm-dash-card p-4 sm:p-5">
        <form className="space-y-3" onSubmit={(e) => void onSubmit(e)}>
          <input
            className="mm-input w-full text-base"
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="Search indexers…"
            aria-label="Search query"
          />
          <div className="flex flex-col gap-3 sm:flex-row sm:flex-wrap sm:items-end">
            <div className="flex flex-wrap gap-1.5" role="group" aria-label="Media type">
              {(
                [
                  { v: "all" as const, label: "All" },
                  { v: "tv" as const, label: "TV" },
                  { v: "movie" as const, label: "Movies" },
                ] as const
              ).map(({ v, label }) => (
                <button
                  key={v}
                  type="button"
                  aria-pressed={mediaType === v}
                  onClick={() => setMediaType(v)}
                  className={[
                    "rounded-full border px-3 py-1.5 text-sm font-medium transition-colors",
                    mediaType === v
                      ? "border-[rgba(212,175,55,0.45)] bg-[var(--mm-accent-soft)] text-[var(--mm-text1)]"
                      : "border-[var(--mm-border)] bg-transparent text-[var(--mm-text2)] hover:bg-white/5",
                  ].join(" ")}
                >
                  {label}
                </button>
              ))}
            </div>
            <div className="min-w-0 flex-1 sm:max-w-md">
              <span id={ixLabel} className="sr-only">
                Indexers
              </span>
              <MmMultiListboxPicker
                className="w-full"
                ariaLabelledBy={ixLabel}
                options={indexerOptions}
                values={indexerValues}
                onChange={setIndexerValues}
                placeholder={enabled.length ? "All enabled (default)" : "No enabled indexers"}
                summaryText={
                  indexerValues.length === 0 || indexerValues.length >= enabled.length ? "All enabled" : `${indexerValues.length} selected`
                }
                disabled={!enabled.length}
              />
            </div>
            <button
              type="submit"
              className={`${mmActionButtonClass({ variant: "primary", disabled: search.isPending || !q.trim() })} w-full sm:w-auto sm:shrink-0`}
              disabled={search.isPending || !q.trim()}
            >
              {search.isPending ? "Searching…" : "Search"}
            </button>
          </div>
          {search.isError ? (
            <div className="rounded-md border border-red-500/30 bg-red-500/10 px-4 py-6 text-center text-sm text-red-200" role="alert">
              {(search.error as Error).message}
            </div>
          ) : null}
        </form>
      </section>

      {!search.isPending && !search.isSuccess && !search.isError ? (
        <div className="rounded-lg border border-[var(--mm-border)] bg-[var(--mm-card-bg)] px-4 py-12 text-center shadow-sm">
          <p className="text-lg text-[var(--mm-text2)]">Search across all your enabled indexers.</p>
          <p className="mt-2 text-sm text-[var(--mm-text3)]">
            Searching across {enabledCount} indexer{enabledCount === 1 ? "" : "s"}.
          </p>
        </div>
      ) : null}

      {search.isPending ? <SearchResultsSkeleton /> : null}

      {search.isSuccess ? (
        rows.length === 0 ? (
          <div className="rounded-lg border border-[var(--mm-border)] bg-[var(--mm-card-bg)] px-4 py-12 text-center shadow-sm">
            <p className="text-sm text-[var(--mm-text2)]">No results found for &quot;{q.trim()}&quot;</p>
          </div>
        ) : (
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {rows.map((r, idx) => {
              const meta = slugToIndexer.get(r.indexer_slug);
              return (
                <ResultCard
                  key={`${r.url}-${idx}`}
                  r={r}
                  indexerName={slugToName.get(r.indexer_slug) ?? r.indexer_slug}
                  privacy={meta?.privacy ?? "public"}
                />
              );
            })}
          </div>
        )
      ) : null}
    </div>
  );
}
