import type { ReactNode } from "react";
import { mmActionButtonClass } from "../../lib/ui/mm-control-roles";

/** Shared overview building blocks: the titled section card and job-list pagination. */

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
      className="mm-card mm-dash-card mm-module-surface"
      aria-labelledby={headingId}
      data-testid={dataTestId}
      data-overview-order={dataOverviewOrder}
    >
      <h2
        id={headingId}
        className="mm-card__title text-lg 2xl:text-xl min-[1760px]:text-2xl"
      >
        {heading}
      </h2>
      <div className="mm-card__body mt-5">{children}</div>
    </section>
  );
}

export function MmJobsPagination({
  page,
  totalPages,
  onPageChange,
  pageSize,
  onPageSizeChange,
  pageSizeOptions = [20, 50, 100],
}: {
  page: number;
  totalPages: number;
  onPageChange: (next: number) => void;
  pageSize: number;
  onPageSizeChange: (next: number) => void;
  pageSizeOptions?: number[];
}) {
  return (
    <div className="flex flex-wrap items-center justify-between gap-2.5 border-t border-[var(--mm-border)] pt-3">
      <div className="flex min-w-0 items-center gap-2 text-xs text-[var(--mm-text3)]">
        <span>Rows per page</span>
        <select
          className="max-w-full rounded border border-[var(--mm-border)] bg-[var(--mm-card-bg)] px-2 py-1 text-xs text-[var(--mm-text2)]"
          value={String(pageSize)}
          onChange={(event) => onPageSizeChange(Number(event.target.value))}
        >
          {pageSizeOptions.map((size) => (
            <option key={size} value={size}>
              {size}
            </option>
          ))}
        </select>
      </div>
      <div className="flex min-w-0 flex-wrap gap-2">
        <p className="self-center text-xs text-[var(--mm-text3)]">
          Page {page} of {totalPages}
        </p>
        <button
          type="button"
          className={mmActionButtonClass({ variant: "secondary" })}
          disabled={page <= 1}
          onClick={() => onPageChange(Math.max(1, page - 1))}
        >
          Previous
        </button>
        <button
          type="button"
          className={mmActionButtonClass({ variant: "secondary" })}
          disabled={page >= totalPages}
          onClick={() => onPageChange(Math.min(totalPages, page + 1))}
        >
          Next
        </button>
      </div>
    </div>
  );
}
