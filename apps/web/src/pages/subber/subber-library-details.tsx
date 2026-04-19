import type { ReactNode } from "react";
import type { SubberSubtitleLangState } from "../../lib/subber/subber-api";
import { subberLanguageLabel } from "../../lib/subber/subber-languages";

export function subberProviderDisplayLabel(key: string | null | undefined): string {
  if (!key) return "—";
  const labels: Record<string, string> = {
    opensubtitles_org: "OpenSubtitles.org",
    opensubtitles_com: "OpenSubtitles.com",
    podnapisi: "Podnapisi",
    subscene: "Subscene",
    addic7ed: "Addic7ed",
  };
  return labels[key] ?? key;
}

function DetailField({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="min-w-0">
      <div className="text-[0.65rem] font-semibold uppercase tracking-wide text-[var(--mm-text2)]">{label}</div>
      <div className="mt-1 text-sm leading-snug text-[var(--mm-text)]">{children}</div>
    </div>
  );
}

/** Monospace path in a bounded, scrollable strip (long UNC / NAS paths). */
export function SubberMediaFilePathBlock({ path }: { path: string }) {
  return (
    <section className="space-y-1.5">
      <h4 className="text-[0.7rem] font-semibold uppercase tracking-wide text-[var(--mm-text2)]">Media file</h4>
      <div className="max-w-full overflow-x-auto rounded-md border border-[var(--mm-border)] bg-black/20 px-2.5 py-2 font-mono text-xs leading-relaxed text-[var(--mm-text)]">
        {path}
      </div>
    </section>
  );
}

export function SubberLanguageTracksDetails({ languages }: { languages: SubberSubtitleLangState[] }) {
  return (
    <section className="space-y-2">
      <h4 className="text-[0.7rem] font-semibold uppercase tracking-wide text-[var(--mm-text2)]">Per-language state</h4>
      <ul className="space-y-2.5">
        {languages.map((l) => (
          <li
            key={l.state_id}
            className="rounded-lg border border-[var(--mm-border)] bg-[var(--mm-card-bg)]/90 px-3 py-3 shadow-sm"
          >
            <p className="border-b border-[var(--mm-border)]/80 pb-2 text-sm font-medium text-[var(--mm-text)]">
              {subberLanguageLabel(l.language_code)}
              <span className="ml-1.5 text-xs font-normal text-[var(--mm-text2)]">({l.language_code})</span>
            </p>
            <div className="mt-3 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
              <DetailField label="Subtitle file">
                <span className="break-all font-mono text-xs">{l.subtitle_path ?? "—"}</span>
              </DetailField>
              <DetailField label="Last search">{l.last_searched_at ?? "—"}</DetailField>
              <DetailField label="Search count">{l.search_count}</DetailField>
              <DetailField label="Source">{l.source ?? "—"}</DetailField>
              <DetailField label="Provider">{subberProviderDisplayLabel(l.provider_key)}</DetailField>
              <DetailField label="Upgrades">
                {(l.upgrade_count ?? 0) > 0 ? `${l.upgrade_count} time(s)` : "None"}
              </DetailField>
            </div>
          </li>
        ))}
      </ul>
    </section>
  );
}

/** Chevron for `<details className="group">` — rotates when open. */
export function SubberDetailsChevron() {
  return (
    <svg
      aria-hidden
      className="h-4 w-4 shrink-0 text-[var(--mm-text2)] transition-transform group-open:rotate-90"
      viewBox="0 0 20 20"
      fill="currentColor"
    >
      <path d="M8 5v10l8-5-8-5z" />
    </svg>
  );
}
