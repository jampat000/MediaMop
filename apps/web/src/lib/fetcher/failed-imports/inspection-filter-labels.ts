import type { FailedImportInspectionFilter } from "./queries";

/** Filter options for Fetcher failed-import task inspection. */
export const FAILED_IMPORT_INSPECTION_FILTER_OPTIONS: { value: FailedImportInspectionFilter; label: string }[] = [
  {
    value: "terminal",
    label: "Finished (default): completed, stopped after errors, needs manual finish",
  },
  {
    value: "handler_ok_finalize_failed",
    label: "Only needs manual finish (handler_ok_finalize_failed)",
  },
  { value: "failed", label: "Only: stopped after errors (failed)" },
  { value: "completed", label: "Only: completed" },
  { value: "pending", label: "Only: queued, waiting (pending)" },
  { value: "leased", label: "Only: in progress (leased)" },
];
