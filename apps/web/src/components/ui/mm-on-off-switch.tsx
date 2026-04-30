/**
 * MediaMop standard **On / Off** segmented control for persisted boolean settings
 * (Enable/Disable, limit hours, etc.). Use `mmActionButtonClass` from `lib/ui/mm-control-roles` for Save/Test/helpers.
 */
export function MmOnOffSwitch({
  id,
  label,
  enabled,
  disabled,
  onChange,
  layout = "default",
}: {
  id: string;
  label: string;
  enabled: boolean;
  disabled: boolean;
  onChange: (v: boolean) => void;
  /** `inline`: label left, On/Off control right (single row). */
  layout?: "default" | "inline";
}) {
  const control = (
    <div
      className="inline-flex w-fit shrink-0 rounded-md border border-[var(--mm-border)] bg-[var(--mm-surface2)]/40 p-0.5"
      role="radiogroup"
      aria-labelledby={id}
    >
      {(["On", "Off"] as const).map((side) => {
        const isOn = side === "On";
        const selected = enabled === isOn;
        return (
          <button
            key={side}
            type="button"
            role="radio"
            aria-checked={selected}
            disabled={disabled}
            onClick={() => onChange(isOn)}
            className={[
              "min-w-[3.25rem] rounded-md px-3 py-1.5 text-sm font-medium transition-colors",
              selected
                ? "bg-[var(--mm-accent-soft)] text-[var(--mm-text1)] shadow-[inset_0_0_0_1px_rgba(212,175,55,0.35)]"
                : "text-[var(--mm-text2)] hover:bg-[var(--mm-card-bg)]/70",
              disabled
                ? "cursor-not-allowed opacity-50 hover:bg-transparent"
                : "",
            ].join(" ")}
          >
            {side}
          </button>
        );
      })}
    </div>
  );

  if (layout === "inline") {
    return (
      <div className="flex w-full min-w-0 flex-row items-center justify-between gap-4">
        <span
          className="min-w-0 flex-1 text-sm font-medium text-[var(--mm-text1)]"
          id={id}
        >
          {label}
        </span>
        {control}
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-2">
      <span className="text-sm font-medium text-[var(--mm-text1)]" id={id}>
        {label}
      </span>
      {control}
    </div>
  );
}
