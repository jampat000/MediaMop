import { useEffect, useId, useRef, useState, type RefObject } from "react";
import {
  mmCheckboxControlClass,
  mmListboxPanelClass,
  mmPickerTriggerClass,
} from "../../lib/ui/mm-control-roles";
import type { MmListboxOption } from "./mm-listbox-picker";

function useCloseOnOutsideAndEscape(
  open: boolean,
  setOpen: (v: boolean) => void,
  containerRef: RefObject<HTMLElement | null>,
) {
  useEffect(() => {
    if (!open) {
      return;
    }
    const onPointerDown = (event: MouseEvent) => {
      const target = event.target as Node | null;
      if (
        containerRef.current &&
        target &&
        !containerRef.current.contains(target)
      ) {
        setOpen(false);
      }
    };
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setOpen(false);
      }
    };
    document.addEventListener("mousedown", onPointerDown);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("mousedown", onPointerDown);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [open, setOpen, containerRef]);
}

type MmMultiListboxPickerProps = {
  options: readonly MmListboxOption[];
  values: readonly string[];
  onChange: (next: string[]) => void;
  disabled?: boolean;
  placeholder?: string;
  /** When set, shown on the closed trigger instead of joined option labels or the placeholder. */
  summaryText?: string;
  "data-testid"?: string;
  ariaLabelledBy?: string;
  ariaDescribedBy?: string;
  className?: string;
};

export function MmMultiListboxPicker({
  options,
  values,
  onChange,
  disabled = false,
  placeholder = "Select one or more…",
  summaryText,
  "data-testid": dataTestId,
  ariaLabelledBy,
  ariaDescribedBy,
  className,
}: MmMultiListboxPickerProps) {
  const autoId = useId();
  const listboxId = `${autoId}-listbox`;
  const [open, setOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement | null>(null);
  useCloseOnOutsideAndEscape(open, setOpen, containerRef);

  const selectedSet = new Set(values);
  const selectedLabels = options
    .filter((o) => selectedSet.has(o.value))
    .map((o) => o.label);
  const triggerLabel =
    summaryText !== undefined
      ? summaryText
      : selectedLabels.length > 0
        ? selectedLabels.join(", ")
        : placeholder;
  const triggerSurface = [
    mmPickerTriggerClass,
    "flex min-h-[2.5rem] items-center justify-between gap-2",
    open && !disabled
      ? "border-[var(--mm-input-border-focus)] !shadow-[inset_0_1px_3px_rgba(0,0,0,0.22),inset_0_1px_0_rgba(255,255,255,0.04),0_0_0_2px_var(--mm-input-focus-ring)]"
      : "",
  ]
    .filter(Boolean)
    .join(" ");

  return (
    <div
      ref={containerRef}
      className={["relative", className].filter(Boolean).join(" ")}
    >
      <button
        type="button"
        className={triggerSurface}
        disabled={disabled}
        aria-haspopup="listbox"
        aria-controls={open ? listboxId : undefined}
        aria-expanded={open}
        aria-labelledby={ariaLabelledBy}
        aria-describedby={ariaDescribedBy}
        data-testid={dataTestId}
        onClick={() => {
          if (!disabled) {
            setOpen((v) => !v);
          }
        }}
      >
        <span className="min-w-0 flex-1 truncate text-left">
          {triggerLabel}
        </span>
        <svg
          aria-hidden
          className={[
            "h-4 w-4 shrink-0 text-[var(--mm-text3)] transition-transform",
            open ? "rotate-180" : "",
          ].join(" ")}
          viewBox="0 0 20 20"
          fill="currentColor"
        >
          <path d="M5.5 7.5 10 12l4.5-4.5H5.5z" />
        </svg>
      </button>
      {open ? (
        <div
          id={listboxId}
          className={mmListboxPanelClass}
          role="listbox"
          aria-multiselectable="true"
        >
          {options.map((opt) => {
            const checked = selectedSet.has(opt.value);
            return (
              <button
                key={opt.value}
                type="button"
                role="option"
                aria-selected={checked}
                className={[
                  "flex w-full items-start gap-3 px-3 py-2 text-left text-sm transition-colors",
                  checked
                    ? "bg-[var(--mm-accent-soft)]/25 text-[var(--mm-text1)]"
                    : "text-[var(--mm-text2)] hover:bg-[var(--mm-accent-soft)] hover:text-[var(--mm-text1)]",
                ].join(" ")}
                onMouseDown={(e) => {
                  e.preventDefault();
                  e.stopPropagation();
                }}
                onClick={(e) => {
                  e.preventDefault();
                  e.stopPropagation();
                  const next = checked
                    ? values.filter((v) => v !== opt.value)
                    : [...values, opt.value];
                  onChange(next);
                }}
              >
                <input
                  type="checkbox"
                  readOnly
                  checked={checked}
                  className={mmCheckboxControlClass}
                  tabIndex={-1}
                />
                <span>{opt.label}</span>
              </button>
            );
          })}
        </div>
      ) : null}
    </div>
  );
}
