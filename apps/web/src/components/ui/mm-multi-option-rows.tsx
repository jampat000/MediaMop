import type { ReactNode } from "react";
import { mmCheckboxControlClass } from "../../lib/ui/mm-control-roles";

/**
 * Grouped **multi-select settings** pattern: independent checkboxes, full-row hit targets.
 * Distinct from binary On/Off (`MmOnOffSwitch`), action buttons (`mmActionButtonClass`), and tabs.
 */
export type MmMultiOptionRowSpec = {
  id: string;
  title: string;
  description?: ReactNode;
  checked: boolean;
  disabled?: boolean;
  onCheckedChange: (next: boolean) => void;
};

const rowBase =
  "flex gap-3 rounded-md border px-3 py-3 text-left text-sm transition-[background-color,border-color,box-shadow] duration-150 focus-within:outline-none focus-within:ring-2 focus-within:ring-[var(--mm-accent-ring)] focus-within:ring-offset-1 focus-within:ring-offset-[var(--mm-card-bg)]";

function rowSurface(checked: boolean, disabled: boolean): string {
  if (disabled) {
    return "border-[var(--mm-border)] bg-[var(--mm-surface2)]/20";
  }
  if (checked) {
    return "border-[rgba(212,175,55,0.28)] bg-[var(--mm-accent-soft)]/28 shadow-[inset_0_0_0_1px_rgba(212,175,55,0.12)] hover:bg-[var(--mm-accent-soft)]/36";
  }
  return "border-[var(--mm-border)] bg-[var(--mm-surface2)]/30 shadow-sm hover:border-[rgba(212,175,55,0.18)] hover:bg-[var(--mm-card-bg)]/55 active:brightness-[0.99]";
}

export function MmMultiOptionRows({
  options,
  ariaLabelledBy,
  "data-testid": testId = "mm-multi-option-rows",
}: {
  options: MmMultiOptionRowSpec[];
  /** Optional id of the heading that labels this option group */
  ariaLabelledBy?: string;
  "data-testid"?: string;
}) {
  return (
    <div
      role="group"
      aria-labelledby={ariaLabelledBy}
      className="flex flex-col gap-2"
      data-testid={testId}
    >
      {options.map((opt) => (
        <label
          key={opt.id}
          htmlFor={opt.id}
          className={[
            rowBase,
            rowSurface(opt.checked, Boolean(opt.disabled)),
            opt.disabled ? "cursor-not-allowed opacity-60" : "cursor-pointer",
          ].join(" ")}
        >
          <input
            id={opt.id}
            type="checkbox"
            className={mmCheckboxControlClass}
            checked={opt.checked}
            disabled={opt.disabled}
            onChange={(e) => opt.onCheckedChange(e.target.checked)}
          />
          <span className="min-w-0 flex-1">
            <span className="block text-sm font-medium text-[var(--mm-text1)]">
              {opt.title}
            </span>
            {opt.description ? (
              <span className="mt-0.5 block text-xs leading-snug text-[var(--mm-text3)]">
                {opt.description}
              </span>
            ) : null}
          </span>
        </label>
      ))}
    </div>
  );
}
