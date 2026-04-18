/**
 * Genre multi-select for Pruner Rules — uses the same `MmMultiListboxPicker` as Refiner subtitle languages.
 */

import type { MmListboxOption } from "../../components/ui/mm-listbox-picker";
import { MmMultiListboxPicker } from "../../components/ui/mm-multi-listbox-picker";

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

const GENRE_LISTBOX_OPTIONS: MmListboxOption[] = PRUNER_RULE_GENRE_OPTIONS.map((g) => ({ value: g, label: g }));

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

function genreTriggerSummary(values: string[]): string {
  if (values.length === 0) return "All genres";
  if (values.length <= 3) {
    const lower = new Set(values.map((v) => v.toLowerCase()));
    return PRUNER_RULE_GENRE_OPTIONS.filter((g) => lower.has(g.toLowerCase())).join(", ");
  }
  return `${values.length} genres selected`;
}

export function PrunerGenreMultiSelect({
  value,
  onChange,
  disabled,
  testId,
  filterHelperText,
  pickerPlaceholder,
}: {
  value: string[];
  onChange: (next: string[]) => void;
  disabled: boolean;
  testId?: string;
  /** When set, replaces the default helper below the picker. Pass "" to hide the helper. */
  filterHelperText?: string;
  /** Trigger / picker placeholder (e.g. "All genres"). */
  pickerPlaceholder?: string;
}) {
  const summary = genreTriggerSummary(value);
  const helper =
    filterHelperText === ""
      ? null
      : (filterHelperText ?? "Pick one or more genres. Leave empty to skip this rule.");
  const placeholder = pickerPlaceholder ?? "All genres";

  return (
    <div className="space-y-2" data-testid={testId ?? "pruner-genre-multiselect"}>
      <span className="sr-only" data-testid="pruner-genre-multiselect-summary">
        {summary}
      </span>
      <MmMultiListboxPicker
        options={GENRE_LISTBOX_OPTIONS}
        values={value}
        onChange={onChange}
        disabled={disabled}
        placeholder={placeholder}
        summaryText={summary}
        data-testid={testId ? `${testId}-picker` : "pruner-genre-multiselect-picker"}
      />
      {helper ? <p className="text-xs text-[var(--mm-text3)]">{helper}</p> : null}
    </div>
  );
}
