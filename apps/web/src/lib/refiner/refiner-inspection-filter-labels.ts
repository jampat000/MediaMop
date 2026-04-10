import type { RefinerInspectionFilter } from "./queries";

/** Select options for the Refiner jobs inspection filter (plain labels; raw status in parentheses where needed). */
export const REFINER_INSPECTION_FILTER_OPTIONS: { value: RefinerInspectionFilter; label: string }[] = [
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
  { value: "leased", label: "Only: running, picked up (leased)" },
];
