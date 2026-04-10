/**
 * Plain labels for persisted job status strings.
 * ``handler_ok_finalize_failed`` must stay distinct from ordinary ``failed`` (never fold together).
 */

export const REFINER_STATUS_HANDLER_OK_FINALIZE_FAILED = "handler_ok_finalize_failed";

export function refinerJobStatusPrimaryLabel(status: string): string {
  switch (status) {
    case REFINER_STATUS_HANDLER_OK_FINALIZE_FAILED:
      return "Needs manual finish — work ran; completion not saved";
    case "failed":
      return "Stopped after errors";
    case "completed":
      return "Completed";
    case "pending":
      return "Queued — waiting to start";
    case "leased":
      return "Running — picked up by a worker";
    default:
      return status;
  }
}

export function isHandlerOkFinalizeFailedStatus(status: string): boolean {
  return status === REFINER_STATUS_HANDLER_OK_FINALIZE_FAILED;
}
