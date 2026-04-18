/**
 * Studio multi-select for Pruner Cleanup — options from live library via {@link usePrunerStudiosQuery}.
 */

import type { MmListboxOption } from "../../components/ui/mm-listbox-picker";
import { MmMultiListboxPicker } from "../../components/ui/mm-multi-listbox-picker";
import { mmPickerTriggerClass } from "../../lib/ui/mm-control-roles";
import { usePrunerStudiosQuery } from "../../lib/pruner/queries";

function studioTriggerSummary(values: string[]): string {
  if (values.length === 0) return "All studios (no filter)";
  if (values.length <= 3) return values.join(", ");
  return `${values.length} studios selected`;
}

function mergeOptionsFromLibrary(libraryStudios: readonly string[], selected: readonly string[]): MmListboxOption[] {
  const byFold = new Map<string, string>();
  for (const s of libraryStudios) {
    const t = s.trim();
    if (!t) continue;
    const k = t.toLowerCase();
    if (!byFold.has(k)) byFold.set(k, t);
  }
  for (const v of selected) {
    const t = v.trim();
    if (!t) continue;
    const k = t.toLowerCase();
    if (!byFold.has(k)) byFold.set(k, t);
  }
  const labels = [...byFold.values()].sort((a, b) => a.localeCompare(b, undefined, { sensitivity: "base" }));
  return labels.map((label) => ({ value: label, label }));
}

export function PrunerStudioMultiSelect({
  value,
  onChange,
  disabled,
  instanceId,
  scope,
  testId,
}: {
  value: string[];
  onChange: (next: string[]) => void;
  disabled: boolean;
  instanceId: number;
  scope: "tv" | "movies";
  testId?: string;
}) {
  const q = usePrunerStudiosQuery(instanceId, scope);
  const loading = q.isPending || q.isFetching;
  const studios = q.data?.studios ?? [];
  const failedOrEmpty = !loading && (q.isError || studios.length === 0);
  const summary = studioTriggerSummary(value);
  const options = mergeOptionsFromLibrary(studios, value);
  const baseTestId = testId ?? "pruner-studio-multiselect";

  if (loading) {
    return (
      <div className="space-y-2" data-testid={baseTestId}>
        <span className="sr-only" data-testid={`${baseTestId}-summary`}>
          {summary}
        </span>
        <p className="text-xs text-[var(--mm-text3)]">
          Select studios to limit this cleanup to content from those studios only. Leave empty to apply your rules to all studios.
        </p>
        <div
          className={`${mmPickerTriggerClass} opacity-70 cursor-not-allowed`}
          data-testid={`${baseTestId}-loading`}
          aria-busy="true"
        >
          Loading studios…
        </div>
      </div>
    );
  }

  if (failedOrEmpty) {
    return (
      <div className="space-y-2" data-testid={baseTestId}>
        <span className="sr-only" data-testid={`${baseTestId}-summary`}>
          {summary}
        </span>
        <p className="text-xs text-[var(--mm-text3)]">
          Select studios to limit this cleanup to content from those studios only. Leave empty to apply your rules to all studios.
        </p>
        <select className="mm-input w-full cursor-not-allowed opacity-70" disabled value="__none__" data-testid={`${baseTestId}-empty`}>
          <option value="__none__">No studios found</option>
        </select>
        <p className="text-xs text-[var(--mm-text3)]">No studios found in your library for this scope.</p>
      </div>
    );
  }

  return (
    <div className="space-y-2" data-testid={baseTestId}>
      <span className="sr-only" data-testid={`${baseTestId}-summary`}>
        {summary}
      </span>
      <p className="text-xs text-[var(--mm-text3)]">
        Select studios to limit this cleanup to content from those studios only. Leave empty to apply your rules to all studios.
      </p>
      <MmMultiListboxPicker
        options={options}
        values={value}
        onChange={onChange}
        disabled={disabled}
        placeholder="All studios (no filter)"
        summaryText={summary}
        data-testid={testId ? `${testId}-picker` : `${baseTestId}-picker`}
      />
    </div>
  );
}
