/**
 * People controls were merged into {@link PrunerProviderRulesCard}. Kept as a no-op export for compatibility with
 * older tests or imports; nothing in the app tree renders this component.
 */
export function PrunerProviderPeopleCard() {
  return null;
}

export function CommaField({
  label,
  placeholder,
  helper,
  value,
  onChange,
  disabled,
}: {
  label: string;
  placeholder: string;
  helper: string;
  value: string;
  onChange: (v: string) => void;
  disabled: boolean;
}) {
  return (
    <label className="block text-sm text-[var(--mm-text2)]">
      <span className="mb-1 block text-xs font-medium text-[var(--mm-text3)]">
        {label}
      </span>
      <input
        type="text"
        className="mm-input w-full"
        placeholder={placeholder}
        value={value}
        disabled={disabled}
        onChange={(e) => onChange(e.target.value)}
      />
      <span className="mt-1 block text-xs text-[var(--mm-text3)]">
        {helper}
      </span>
    </label>
  );
}

export function YearRange({
  min,
  max,
  onMin,
  onMax,
  disabled,
  helperText,
  title,
}: {
  min: string;
  max: string;
  onMin: (v: string) => void;
  onMax: (v: string) => void;
  disabled: boolean;
  helperText?: string;
  /** Section label above min/max inputs (default: year range). */
  title?: string;
}) {
  return (
    <div className="space-y-1">
      <span className="text-xs font-medium text-[var(--mm-text3)]">
        {title ?? "Only these years"}
      </span>
      <div className="flex flex-wrap items-end gap-3">
        <label className="text-sm text-[var(--mm-text2)]">
          Min year
          <input
            type="text"
            inputMode="numeric"
            className="mm-input ml-2 w-28"
            value={min}
            disabled={disabled}
            onChange={(e) => onMin(e.target.value)}
          />
        </label>
        <label className="text-sm text-[var(--mm-text2)]">
          Max year
          <input
            type="text"
            inputMode="numeric"
            className="mm-input ml-2 w-28"
            value={max}
            disabled={disabled}
            onChange={(e) => onMax(e.target.value)}
          />
        </label>
      </div>
      <p className="text-xs text-[var(--mm-text3)]">
        {helperText ?? "Leave blank for all years."}
      </p>
    </div>
  );
}
