import { mmActionButtonClass } from "../../lib/ui/mm-control-roles";

const STORAGE_KEY = "mediamop.subber.libraryPageSize";

export const SUBBER_LIBRARY_PAGE_SIZES = [20, 50, 100] as const;

export type SubberLibraryPageSize = (typeof SUBBER_LIBRARY_PAGE_SIZES)[number];

export function readSubberLibraryPageSize(): SubberLibraryPageSize {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    const n = Number(raw);
    if (n === 20 || n === 50 || n === 100) {
      return n;
    }
  } catch {
    /* ignore */
  }
  return 20;
}

export function writeSubberLibraryPageSize(n: SubberLibraryPageSize): void {
  try {
    localStorage.setItem(STORAGE_KEY, String(n));
  } catch {
    /* ignore */
  }
}

type SubberLibraryPagerProps = {
  /** Total rows matching filters (movies or TV episodes). */
  total: number;
  page: number;
  pageSize: SubberLibraryPageSize;
  onPageChange: (page: number) => void;
  onPageSizeChange: (size: SubberLibraryPageSize) => void;
  itemLabel: string;
};

export function SubberLibraryPager({
  total,
  page,
  pageSize,
  onPageChange,
  onPageSizeChange,
  itemLabel,
}: SubberLibraryPagerProps) {
  const pageCount = Math.max(1, Math.ceil(total / pageSize) || 1);
  const safePage = Math.min(page, Math.max(0, pageCount - 1));
  const start = total === 0 ? 0 : safePage * pageSize + 1;
  const end = Math.min(total, (safePage + 1) * pageSize);
  const canPrev = safePage > 0;
  const canNext = (safePage + 1) * pageSize < total;

  return (
    <div className="flex flex-col gap-3 rounded-lg border border-[var(--mm-border)] bg-[var(--mm-card-bg)]/40 px-3 py-3 sm:flex-row sm:flex-wrap sm:items-center sm:justify-between">
      <p className="text-sm text-[var(--mm-text2)]">
        {total === 0 ? (
          <>No {itemLabel} match the current filters.</>
        ) : (
          <>
            Showing <span className="font-medium text-[var(--mm-text)]">{start}</span>
            {"–"}
            <span className="font-medium text-[var(--mm-text)]">{end}</span> of{" "}
            <span className="font-medium text-[var(--mm-text)]">{total}</span> {itemLabel}
          </>
        )}
      </p>
      <div className="flex flex-wrap items-center gap-2 sm:gap-3">
        <label className="flex items-center gap-2 text-xs text-[var(--mm-text2)]">
          Per page
          <select
            className="mm-input py-1 text-sm"
            value={pageSize}
            onChange={(e) => {
              const v = Number(e.target.value) as SubberLibraryPageSize;
              onPageSizeChange(v);
            }}
            aria-label="Items per page"
          >
            {SUBBER_LIBRARY_PAGE_SIZES.map((n) => (
              <option key={n} value={n}>
                {n}
              </option>
            ))}
          </select>
        </label>
        <div className="flex items-center gap-1.5">
          <button
            type="button"
            className={mmActionButtonClass({ variant: "secondary" })}
            disabled={!canPrev}
            onClick={() => onPageChange(safePage - 1)}
            aria-label="Previous page"
          >
            Previous
          </button>
          <span className="min-w-[5.5rem] text-center text-xs text-[var(--mm-text2)]">
            Page {safePage + 1} / {pageCount}
          </span>
          <button
            type="button"
            className={mmActionButtonClass({ variant: "secondary" })}
            disabled={!canNext}
            onClick={() => onPageChange(safePage + 1)}
            aria-label="Next page"
          >
            Next
          </button>
        </div>
      </div>
    </div>
  );
}
