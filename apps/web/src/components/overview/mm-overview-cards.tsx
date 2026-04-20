import type { ReactNode } from "react";
import { fetcherMenuButtonClass } from "../../pages/fetcher/fetcher-menu-button";

/**
 * Shared overview card components used by all four module overview tabs.
 * Single source of truth for card layout, heading style, stat tiles,
 * needs attention list, and next steps navigation.
 */

// ─── Inner at-a-glance card ────────────────────────────────────────────────

export function MmAtGlanceCard({
  title,
  body,
  glanceOrder,
  emphasis,
  footer,
  gridClassName,
  size = "default",
  fillRowHeight = true,
  "data-testid": dataTestId,
}: {
  title: string;
  body: ReactNode;
  glanceOrder: "1" | "2" | "3" | "4" | "5";
  emphasis?: boolean;
  footer?: ReactNode;
  gridClassName?: string;
  size?: "default" | "large";
  /** When false, the card stays content-height in a CSS grid row (avoids a tall empty body when a sibling card is taller). */
  fillRowHeight?: boolean;
  "data-testid"?: string;
}) {
  const large = size === "large";
  return (
    <div
      className={[
        "flex min-h-0 min-w-0 flex-col rounded-md border border-[var(--mm-border)] text-sm",
        fillRowHeight ? "h-full" : "h-auto self-start w-full",
        large ? "gap-4 p-5 lg:gap-5 lg:p-6" : "gap-3.5 p-5 lg:gap-4 lg:p-6",
        emphasis
          ? "bg-[var(--mm-card-bg)] shadow-[inset_0_1px_0_0_rgba(255,255,255,0.04)]"
          : "bg-[var(--mm-card-bg)]/70",
        large ? "lg:text-[0.9375rem] lg:leading-relaxed" : "",
        gridClassName ?? "",
      ]
        .filter(Boolean)
        .join(" ")}
      data-at-glance-order={glanceOrder}
      data-testid={dataTestId}
    >
      <h3 className="break-words text-sm font-semibold text-[var(--mm-text1)]">{title}</h3>
      <div
        className={[
          "min-w-0 break-words text-[var(--mm-text2)]",
          fillRowHeight ? "min-h-0 flex-1" : "",
          large ? "mt-1 lg:mt-1.5" : "",
        ]
          .filter(Boolean)
          .join(" ")}
      >
        {body}
      </div>
      {footer ? (
        <div
          className={["mt-auto border-t border-[var(--mm-border)]", large ? "pt-4 lg:pt-5" : "pt-3"].join(" ")}
        >
          {footer}
        </div>
      ) : null}
    </div>
  );
}

// ─── Stat tile (bold number with label) ───────────────────────────────────

export function MmStatTile({
  label,
  value,
}: {
  label: string;
  value: ReactNode;
}) {
  return (
    <div className="min-w-0 rounded-md bg-black/15 px-2 py-3 text-center sm:px-3">
      <span className="block text-[0.65rem] font-semibold uppercase tracking-wide text-[var(--mm-text3)]">{label}</span>
      <span className="mt-1 block break-words text-2xl font-bold tabular-nums leading-tight text-[var(--mm-text1)]">{value}</span>
    </div>
  );
}

// ─── Stat tile row (3 tiles) ──────────────────────────────────────────────

export function MmStatTileRow({ children }: { children: ReactNode }) {
  return <div className="grid grid-cols-3 gap-2 sm:gap-3">{children}</div>;
}

// ─── Stat caption ─────────────────────────────────────────────────────────

export function MmStatCaption({ children }: { children: ReactNode }) {
  return <p className="mt-4 text-[0.7rem] leading-snug text-[var(--mm-text3)]">{children}</p>;
}

// ─── Outer section wrapper ────────────────────────────────────────────────

export function MmOverviewSection({
  id,
  headingId,
  heading,
  children,
  "data-testid": dataTestId,
  "data-overview-order": dataOverviewOrder,
}: {
  id?: string;
  headingId: string;
  heading: string;
  children: ReactNode;
  "data-testid"?: string;
  "data-overview-order"?: string;
}) {
  return (
    <section
      id={id}
      className="mm-card mm-dash-card mm-fetcher-module-surface"
      aria-labelledby={headingId}
      data-testid={dataTestId}
      data-overview-order={dataOverviewOrder}
    >
      <h2 id={headingId} className="mm-card__title text-lg">
        {heading}
      </h2>
      <div className="mm-card__body mt-5">{children}</div>
    </section>
  );
}

// ─── At a glance grid ─────────────────────────────────────────────────────

export function MmAtGlanceGrid({
  children,
  className,
}: {
  children: ReactNode;
  className?: string;
}) {
  return (
    <div
      className={
        className ??
        "grid grid-cols-1 gap-4 sm:grid-cols-2 sm:gap-x-5 sm:gap-y-5 lg:grid-cols-3 lg:gap-x-5 lg:gap-y-5"
      }
    >
      {children}
    </div>
  );
}

// ─── Needs attention list ─────────────────────────────────────────────────

export function MmNeedsAttentionList({
  items,
  actions,
  emptyMessage = "Everything looks good.",
}: {
  items: string[];
  actions?: ReactNode;
  /** When `items` is empty; module-specific copy without changing list-building logic. */
  emptyMessage?: string;
}) {
  if (items.length === 0) {
    return <p className="text-sm text-[var(--mm-text1)]">{emptyMessage}</p>;
  }
  return (
    <div className="text-sm text-[var(--mm-text2)]">
      <ul className="list-none space-y-3 border-l-2 border-[var(--mm-border)] pl-3.5">
        {items.map((text, i) => (
          <li key={`${text}-${i}`} className="break-words leading-snug text-[var(--mm-text1)]">
            {text}
          </li>
        ))}
      </ul>
      {actions ? <div className="mt-5 flex flex-wrap gap-2.5 border-t border-[var(--mm-border)] pt-4">{actions}</div> : null}
    </div>
  );
}

// ─── Next steps nav button ────────────────────────────────────────────────

export function MmNextStepsButton({
  label,
  onClick,
}: {
  label: string;
  onClick: () => void;
}) {
  return (
    <button type="button" className={fetcherMenuButtonClass({ variant: "secondary" })} onClick={onClick}>
      {label}
    </button>
  );
}
