/**
 * Hard-coded genre pick list for Pruner Rules (matches common Jellyfin / Emby / Plex genre strings).
 * Pills use the same pressed / unpressed styling as weekday chips in Fetcher ARR schedules (MmScheduleDayChips).
 */

export const PRUNER_RULE_GENRE_OPTIONS = [
  "Action",
  "Adventure",
  "Animation",
  "Comedy",
  "Crime",
  "Documentary",
  "Drama",
  "Family",
  "Fantasy",
  "History",
  "Horror",
  "Music",
  "Mystery",
  "Romance",
  "Science Fiction",
  "Thriller",
  "War",
  "Western",
] as const;

const GENRE_PILL_CLASS = (on: boolean, disabled: boolean) =>
  [
    "rounded-md border px-2 py-1 text-xs font-medium transition-colors",
    on
      ? "border-[rgba(212,175,55,0.45)] bg-[var(--mm-accent-soft)] text-[var(--mm-text1)]"
      : "border-[var(--mm-border)] bg-transparent text-[var(--mm-text2)] hover:bg-[var(--mm-card-bg)]/60",
    disabled ? "cursor-not-allowed opacity-50" : "",
  ].join(" ");

/** Map saved API genres onto canonical list entries (case-insensitive). */
export function prunerGenresFromApi(api: string[] | undefined | null): string[] {
  if (!api?.length) return [];
  const out: string[] = [];
  for (const canon of PRUNER_RULE_GENRE_OPTIONS) {
    if (api.some((a) => a.trim().toLowerCase() === canon.toLowerCase())) {
      out.push(canon);
    }
  }
  return out;
}

export function PrunerGenreMultiSelect({
  value,
  onChange,
  disabled,
  testId,
}: {
  value: string[];
  onChange: (next: string[]) => void;
  disabled: boolean;
  testId?: string;
}) {
  const n = value.length;
  const summary = n === 0 ? "All genres" : `${n} genre${n === 1 ? "" : "s"} selected`;

  function toggle(g: string) {
    const lower = g.toLowerCase();
    const has = value.some((x) => x.toLowerCase() === lower);
    if (has) {
      onChange(value.filter((x) => x.toLowerCase() !== lower));
    } else {
      onChange([...value, g]);
    }
  }

  return (
    <div className="space-y-2" data-testid={testId ?? "pruner-genre-multiselect"}>
      <p className="text-xs font-medium text-[var(--mm-text2)]" data-testid="pruner-genre-multiselect-summary">
        {summary}
      </p>
      <p className="text-xs text-[var(--mm-text3)]">
        Leave none selected to include every genre. Pick one or more to limit scans to those genres only.
      </p>
      <div className="flex flex-wrap gap-1.5" role="group" aria-label="Genres">
        {PRUNER_RULE_GENRE_OPTIONS.map((g) => {
          const selected = value.some((x) => x.toLowerCase() === g.toLowerCase());
          return (
            <button
              key={g}
              type="button"
              disabled={disabled}
              aria-pressed={selected}
              onClick={() => toggle(g)}
              className={GENRE_PILL_CLASS(selected, disabled)}
            >
              {g}
            </button>
          );
        })}
      </div>
    </div>
  );
}
