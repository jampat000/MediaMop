import type { FetcherJobsInspectionFilter } from "./queries";

/** Filter labels for the Fetcher jobs history table — plain language first. */
export const FETCHER_JOBS_INSPECTION_FILTER_OPTIONS: { value: FetcherJobsInspectionFilter; label: string }[] = [
  {
    value: "terminal",
    label: "Finished (default): done, stopped with errors, or needs your OK to close",
  },
  {
    value: "handler_ok_finalize_failed",
    label: "Only: needs your OK to close (storage: handler_ok_finalize_failed)",
  },
  { value: "failed", label: "Only: stopped with errors" },
  { value: "completed", label: "Only: completed" },
  { value: "pending", label: "Only: waiting to start" },
  { value: "leased", label: "Only: running now" },
];
