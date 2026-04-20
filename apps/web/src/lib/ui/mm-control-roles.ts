/**
 * MediaMop-wide **control roles** (action buttons + section tabs).
 *
 * Hierarchy (Fetcher is the reference surface):
 * - **primary** — commit/save (Save, Apply, Confirm, …)
 * - **secondary** — non-commit utilities (Test, Open, Run now, Queue …, Retry, Refresh)
 * - **tertiary** — lower-emphasis helpers (Show/Hide, Clear, compact row actions)
 *
 * Binary booleans use the segmented On/Off control (`MmOnOffSwitch` / `FetcherEnableSwitch`), not these classes.
 */

const actionBase =
  "inline-flex min-h-[2.5rem] max-w-full items-center justify-center rounded-md border px-4 py-2.5 text-sm font-semibold leading-snug tracking-normal transition-all duration-150 whitespace-normal text-center";

const tertiaryBase =
  "inline-flex min-h-[2.25rem] max-w-full items-center justify-center rounded-md border px-3 py-1.5 text-sm font-medium leading-snug tracking-normal transition-all duration-150 whitespace-normal text-center";

/**
 * Default class for ordinary editable text inputs (paths, titles, CSV tokens, etc.).
 * Use the UI body font — not monospace unless the value is truly technical read-only display.
 */
export const mmEditableTextFieldClass = "mm-input w-full min-w-0";

/**
 * Shared layout/interaction for native selects and anchored listbox triggers.
 * Visual chrome (inset, border, height, padding, focus) lives on `.mm-input` in `mediamop-shell.css`.
 */
const mmNativeFieldShell =
  "mm-input w-full min-w-0 text-sm text-[var(--mm-text)] transition-[border-color,background-color,box-shadow] duration-150 " +
  "focus-visible:outline-none disabled:cursor-not-allowed";

/** Native dropdown / listbox-style ``<select>`` — use under a field label (includes top spacing). */
export const mmSelectFieldClass = `${mmNativeFieldShell} mt-1 cursor-pointer`;

/** Anchored picker button (custom listbox) — visually aligned with {@link mmSelectFieldClass}. */
export const mmPickerTriggerClass = `${mmNativeFieldShell} mt-1 cursor-pointer text-left`;

/** Checkbox control — matches ``MmMultiOptionRows`` / Fetcher multi-option styling. */
export const mmCheckboxControlClass =
  "mt-0.5 h-4 w-4 shrink-0 rounded border-[var(--mm-border)] text-[var(--mm-gold)] accent-[var(--mm-gold)] " +
  "focus:outline-none focus-visible:ring-2 focus-visible:ring-[var(--mm-accent-ring)] focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--mm-card-bg)] " +
  "disabled:cursor-not-allowed disabled:opacity-50";

/** Dropdown panel for {@link mmPickerTriggerClass} — matches Global Settings timezone listbox. */
export const mmListboxPanelClass =
  "absolute z-20 mt-1 max-h-64 w-full min-w-0 overflow-auto rounded border border-[var(--mm-border)] bg-[var(--mm-card-bg)] py-1 shadow-lg";

export function mmListboxOptionButtonClass(selected: boolean): string {
  return [
    "block w-full px-3 py-2 text-left text-sm transition-colors",
    selected
      ? "bg-[var(--mm-accent-soft)] text-[var(--mm-text1)]"
      : "text-[var(--mm-text2)] hover:bg-[var(--mm-accent-soft)] hover:text-[var(--mm-text1)]",
  ].join(" ");
}

/** Monospace for read-only technical strings (resolved paths, env keys, raw ids). */
export const mmTechnicalMonoSmallClass = "font-mono text-xs break-all text-[var(--mm-text2)]";

/** In-page section tabs (e.g. Fetcher Overview / Connections). Not sidebar navigation. */
export function mmSectionTabClass(active: boolean): string {
  return [
    "inline-flex min-h-[2.25rem] shrink-0 items-center justify-center whitespace-nowrap rounded-md border px-3 py-1.5 text-sm font-medium transition-colors",
    "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--mm-accent-ring)] focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--mm-bg-main)]",
    active
      ? "border-[var(--mm-gold)] bg-[var(--mm-accent-soft)] text-[var(--mm-text)]"
      : "border-[var(--mm-border)] bg-transparent text-[var(--mm-text2)] hover:bg-[var(--mm-card-bg)]",
  ].join(" ");
}

export function mmActionButtonClass(opts: {
  variant: "primary" | "secondary" | "tertiary";
  disabled?: boolean;
}): string {
  const { variant, disabled } = opts;

  if (variant === "tertiary") {
    if (disabled) {
      return [
        tertiaryBase,
        "cursor-not-allowed border-[var(--mm-border)] bg-transparent text-[var(--mm-text3)] opacity-60",
      ].join(" ");
    }
    return [
      tertiaryBase,
      "cursor-pointer border-[var(--mm-border)] bg-transparent text-[var(--mm-text2)]",
      "hover:border-[var(--mm-border)] hover:bg-[var(--mm-card-bg)]/55 hover:text-[var(--mm-text1)]",
      "active:brightness-[0.98]",
      "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--mm-accent-ring)] focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--mm-card-bg)]",
    ].join(" ");
  }

  if (variant === "primary") {
    if (disabled) {
      return [
        actionBase,
        "cursor-not-allowed border-[var(--mm-border)] bg-[rgba(31,35,42,0.35)] text-[var(--mm-text3)] opacity-80",
      ].join(" ");
    }
    return [
      actionBase,
      "cursor-pointer border-[var(--mm-gold)] bg-[rgba(212,175,55,0.2)] text-[var(--mm-text)] shadow-[0_2px_14px_rgba(212,175,55,0.14)]",
      "hover:border-[var(--mm-gold-bright)] hover:bg-[rgba(212,175,55,0.28)] hover:shadow-[0_4px_20px_rgba(212,175,55,0.22)] hover:-translate-y-px",
      "active:translate-y-0 active:brightness-[0.97]",
      "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--mm-accent-ring)] focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--mm-card-bg)]",
    ].join(" ");
  }

  if (disabled) {
    return [
      actionBase,
      "cursor-not-allowed border-[var(--mm-border)] bg-transparent text-[var(--mm-text3)] opacity-70",
    ].join(" ");
  }
  return [
    actionBase,
    "cursor-pointer border-[var(--mm-border)] bg-[rgba(31,35,42,0.45)] text-[var(--mm-text)]",
    "hover:border-[rgba(212,175,55,0.55)] hover:bg-[var(--mm-accent-soft)] hover:shadow-sm",
    "active:brightness-[0.97]",
    "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--mm-accent-ring)] focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--mm-card-bg)]",
  ].join(" ");
}
