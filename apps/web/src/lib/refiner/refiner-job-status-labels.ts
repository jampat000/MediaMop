/**
 * Human labels for persisted ``refiner_jobs.status`` strings.
 * ``handler_ok_finalize_failed`` must stay explicit — not folded into generic “failed”.
 */

export const REFINER_STATUS_HANDLER_OK_FINALIZE_FAILED = "handler_ok_finalize_failed";

export function refinerJobStatusPrimaryLabel(status: string): string {
  switch (status) {
    case REFINER_STATUS_HANDLER_OK_FINALIZE_FAILED:
      return "Handler succeeded — finalize failed";
    case "failed":
      return "Failed (handler or retries exhausted)";
    case "completed":
      return "Completed";
    case "pending":
      return "Pending";
    case "leased":
      return "Leased";
    default:
      return status;
  }
}

export function isHandlerOkFinalizeFailedStatus(status: string): boolean {
  return status === REFINER_STATUS_HANDLER_OK_FINALIZE_FAILED;
}
