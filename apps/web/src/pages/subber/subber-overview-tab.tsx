import { subberLanguageLabel } from "../../lib/subber/subber-languages";
import { useSubberOverviewQuery } from "../../lib/subber/subber-queries";

export function SubberOverviewTab() {
  const q = useSubberOverviewQuery();
  if (q.isLoading) return <p className="text-sm text-[var(--mm-text2)]">Loading overview…</p>;
  if (q.isError) return <p className="text-sm text-red-600">{(q.error as Error).message}</p>;
  const d = q.data;
  if (!d) return null;
  return (
    <div className="space-y-6" data-testid="subber-overview-tab">
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-5">
        <Stat label="Total tracked" value={d.total_tracked} />
        <Stat label="Subtitles found" value={d.found} />
        <Stat label="Still missing" value={d.missing} />
        <Stat label="Searches today" value={d.searches_today} />
        <Stat label="Upgraded" value={d.upgraded_tracks ?? 0} />
      </div>
      <section>
        <h2 className="text-base font-semibold text-[var(--mm-text)]">Per language</h2>
        <div className="mt-2 overflow-x-auto rounded border border-[var(--mm-border)]">
          <table className="w-full min-w-[28rem] text-left text-sm">
            <thead className="bg-black/20 text-[var(--mm-text2)]">
              <tr>
                <th className="px-3 py-2">Language</th>
                <th className="px-3 py-2">Found</th>
                <th className="px-3 py-2">Missing</th>
                <th className="px-3 py-2">Total</th>
              </tr>
            </thead>
            <tbody>
              {d.per_language.map((row) => (
                <tr key={row.language} className="border-t border-[var(--mm-border)]">
                  <td className="px-3 py-2 text-[var(--mm-text)]">{subberLanguageLabel(String(row.language))}</td>
                  <td className="px-3 py-2">{row.found}</td>
                  <td className="px-3 py-2">{row.missing}</td>
                  <td className="px-3 py-2">{row.total}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
      <section className="space-y-2 text-sm leading-relaxed text-[var(--mm-text2)]">
        <h2 className="text-base font-semibold text-[var(--mm-text)]">How it works</h2>
        <ol className="list-decimal space-y-2 pl-5">
          <li>When Radarr or Sonarr imports a file, Subber searches OpenSubtitles immediately for subtitles in your chosen languages.</li>
          <li>
            On a schedule, Subber checks your library for files still missing subtitles and searches for them automatically. You can also sync your full Radarr and Sonarr libraries manually from Settings.
          </li>
          <li>You can also trigger a search manually from the TV or Movies tab.</li>
          <li>
            Subtitle files are saved next to your media and named to match — for example{" "}
            <code className="rounded bg-black/25 px-1 font-mono text-[0.85em]">Movie.2023.en.srt</code> alongside{" "}
            <code className="rounded bg-black/25 px-1 font-mono text-[0.85em]">Movie.2023.mkv</code>. Plex, Emby and Jellyfin pick them up automatically.
          </li>
          <li>Your languages are tried in the order you set in Settings. If your first language is not found, Subber tries the next automatically.</li>
          <li>
            Subber can periodically re-search for better quality subtitles for files that already have one. Enable subtitle upgrade in the Schedule tab (and turn on upgrades in Settings).
          </li>
        </ol>
      </section>
      <p className="rounded-md border border-amber-500/40 bg-amber-500/10 px-3 py-2 text-sm text-[var(--mm-text)]">
        Subber downloads SRT subtitles only. Your Sonarr and Radarr connections are configured in Settings — they are pre-filled from Fetcher if available but kept fully independent.
      </p>
    </div>
  );
}

function Stat({ label, value }: { label: string; value: number }) {
  return (
    <div className="rounded-lg border border-[var(--mm-border)] bg-black/15 px-3 py-2">
      <p className="text-xs text-[var(--mm-text2)]">{label}</p>
      <p className="text-2xl font-semibold text-[var(--mm-text)]">{value}</p>
    </div>
  );
}
