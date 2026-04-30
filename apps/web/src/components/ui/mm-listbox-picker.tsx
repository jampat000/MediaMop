import { useEffect, useId, useRef, useState, type RefObject } from "react";
import {
  mmListboxOptionButtonClass,
  mmListboxPanelClass,
  mmPickerTriggerClass,
} from "../../lib/ui/mm-control-roles";

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

export type MmListboxOption = { value: string; label: string };

type MmListboxPickerProps = {
  options: readonly MmListboxOption[];
  value: string;
  onChange: (next: string) => void;
  disabled?: boolean;
  placeholder?: string;
  "data-testid"?: string;
  /** Use with a visible `<span id={…}>` label (same pattern as Global Settings timezone). */
  ariaLabelledBy?: string;
  ariaDescribedBy?: string;
  /** Optional width constraint on the anchor (e.g. `max-w-md`). */
  className?: string;
};

/**
 * Custom listbox picker — **visual and interaction parity** with Global Settings → Timezone
 * (anchored panel, option rows, click-outside, Escape).
 */
export function MmListboxPicker({
  options,
  value,
  onChange,
  disabled = false,
  placeholder = "Select…",
  "data-testid": dataTestId,
  ariaLabelledBy,
  ariaDescribedBy,
  className,
}: MmListboxPickerProps) {
  const autoId = useId();
  const listboxId = `${autoId}-listbox`;
  const [open, setOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement | null>(null);
  useCloseOnOutsideAndEscape(open, setOpen, containerRef);

  const selected = options.find((o) => o.value === value);
  const triggerLabel = selected?.label ?? placeholder;
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
        <div id={listboxId} className={mmListboxPanelClass} role="listbox">
          {options.map((opt) => (
            <button
              key={opt.value === "" ? "__empty__" : opt.value}
              type="button"
              role="option"
              aria-selected={opt.value === value}
              className={mmListboxOptionButtonClass(opt.value === value)}
              onMouseDown={(e) => {
                e.preventDefault();
                e.stopPropagation();
              }}
              onClick={(e) => {
                e.preventDefault();
                e.stopPropagation();
                onChange(opt.value);
                setOpen(false);
              }}
            >
              {opt.label}
            </button>
          ))}
        </div>
      ) : null}
    </div>
  );
}
