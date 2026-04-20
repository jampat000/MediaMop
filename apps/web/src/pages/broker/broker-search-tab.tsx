import { useId, useMemo, useState } from "react";
import { MmListboxPicker } from "../../components/ui/mm-listbox-picker";
import { MmMultiListboxPicker } from "../../components/ui/mm-multi-listbox-picker";
import type { BrokerResult } from "../../lib/broker/broker-api";
import { useBrokerIndexersQuery, useBrokerSearchMutation } from "../../lib/broker/broker-queries";
import { mmActionButtonClass } from "../../lib/ui/mm-control-roles";

const TYPE_OPTIONS = [
  { value: "all", label: "All" },
  { value: "tv", label: "TV" },
  { value: "movie", label: "Movies" },
] as const;

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

export function BrokerSearchTab() {
  const ix = useBrokerIndexersQuery();
  const search = useBrokerSearchMutation();

  const qLabel = useId();
  const typeLabel = useId();
  const ixLabel = useId();

  const [q, setQ] = useState("");
  const [mediaType, setMediaType] = useState<string>("all");
  const [indexerValues, setIndexerValues] = useState<string[]>([]);

  const enabled = useMemo(() => (ix.data ?? []).filter((i) => i.enabled), [ix.data]);
  const indexerOptions = useMemo(
    () => enabled.map((i) => ({ value: String(i.id), label: i.name })),
    [enabled],
  );

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

  return (
    <div className="space-y-6" data-testid="broker-search-tab">
      <form
        className="space-y-4 rounded-lg border border-[var(--mm-border)] bg-[var(--mm-card-bg)] p-5 shadow-sm"
        onSubmit={(e) => void onSubmit(e)}
      >
        <label className="block">
          <span id={qLabel} className="text-sm font-medium text-[var(--mm-text)]">
            Query
          </span>
          <input
            className="mm-input mt-1 w-full max-w-2xl"
            value={q}
            onChange={(e) => setQ(e.target.value)}
            aria-labelledby={qLabel}
            placeholder="Search titles…"
          />
        </label>
        <div className="grid gap-4 sm:grid-cols-2 lg:max-w-4xl">
          <label className="block">
            <span id={typeLabel} className="text-xs font-semibold uppercase tracking-wide text-[var(--mm-text3)]">
              Type
            </span>
            <MmListboxPicker
              className="mt-2"
              ariaLabelledBy={typeLabel}
              options={TYPE_OPTIONS.map((o) => ({ value: o.value, label: o.label }))}
              value={mediaType}
              onChange={(v) => setMediaType(v)}
            />
          </label>
          <label className="block min-w-0">
            <span id={ixLabel} className="text-xs font-semibold uppercase tracking-wide text-[var(--mm-text3)]">
              Indexers
            </span>
            <MmMultiListboxPicker
              className="mt-2"
              ariaLabelledBy={ixLabel}
              options={indexerOptions}
              values={indexerValues}
              onChange={setIndexerValues}
              placeholder={enabled.length ? "All enabled (default)" : "No enabled indexers"}
              summaryText={
                indexerValues.length === 0 || indexerValues.length >= enabled.length
                  ? "All enabled"
                  : `${indexerValues.length} selected`
              }
              disabled={!enabled.length}
            />
            <p className="mt-1 text-xs text-[var(--mm-text3)]">Leave unset to search every enabled indexer.</p>
          </label>
        </div>
        <button
          type="submit"
          className={mmActionButtonClass({ variant: "primary", disabled: search.isPending || !q.trim() })}
          disabled={search.isPending || !q.trim()}
        >
          {search.isPending ? "Searching…" : "Search"}
        </button>
        {search.isError ? (
          <p className="text-sm text-red-400" role="alert">
            {(search.error as Error).message}
          </p>
        ) : null}
      </form>

      {search.isPending ? (
        <p className="text-sm text-[var(--mm-text2)]">Searching…</p>
      ) : search.isSuccess ? (
        rows.length === 0 ? (
          <p className="text-sm text-[var(--mm-text2)]">No results found</p>
        ) : (
          <div className="overflow-x-auto rounded-lg border border-[var(--mm-border)] bg-[var(--mm-card-bg)] shadow-sm">
            <table className="w-full min-w-[48rem] text-left text-sm">
              <thead className="border-b border-[var(--mm-border)] bg-black/15 text-[var(--mm-text2)]">
                <tr>
                  <th className="px-3 py-2 font-medium">Title</th>
                  <th className="px-3 py-2 font-medium">Indexer</th>
                  <th className="px-3 py-2 font-medium">Protocol</th>
                  <th className="px-3 py-2 font-medium">Size</th>
                  <th className="px-3 py-2 font-medium">Seeders</th>
                  <th className="px-3 py-2 font-medium">Age</th>
                  <th className="px-3 py-2 font-medium">Actions</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((r, idx) => (
                  <tr key={`${r.url}-${idx}`} className="border-t border-[var(--mm-border)]">
                    <td className="max-w-xs px-3 py-2 align-top text-[var(--mm-text1)]">{r.title}</td>
                    <td className="px-3 py-2 align-top font-mono text-xs text-[var(--mm-text2)]">{r.indexer_slug}</td>
                    <td className="px-3 py-2 align-top capitalize text-[var(--mm-text2)]">{r.protocol}</td>
                    <td className="px-3 py-2 align-top tabular-nums text-[var(--mm-text2)]">{formatBytes(r.size)}</td>
                    <td className="px-3 py-2 align-top tabular-nums text-[var(--mm-text2)]">
                      {r.seeders ?? "—"}
                    </td>
                    <td className="px-3 py-2 align-top text-xs text-[var(--mm-text2)]">{relativeAge(r.published_at)}</td>
                    <td className="px-3 py-2 align-top">
                      <div className="flex flex-wrap gap-2">
                        {r.magnet ? (
                          <a
                            className={mmActionButtonClass({ variant: "secondary" })}
                            href={r.magnet}
                            rel="noreferrer"
                          >
                            Magnet
                          </a>
                        ) : null}
                        <a
                          className={mmActionButtonClass({ variant: "secondary" })}
                          href={r.url}
                          target="_blank"
                          rel="noreferrer"
                        >
                          Link
                        </a>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )
      ) : null}
    </div>
  );
}
