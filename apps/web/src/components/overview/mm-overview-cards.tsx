import { mmActionButtonClass } from "../../lib/ui/mm-control-roles";

/** Job-list pagination, shared by the Overview and the Jobs tab. */

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
