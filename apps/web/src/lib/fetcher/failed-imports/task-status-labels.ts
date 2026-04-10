/**
 * Plain labels for persisted task status strings (Fetcher failed-import queue workflow).
 * handler_ok_finalize_failed must stay distinct from ordinary failed.
 */

export const FAILED_IMPORT_STATUS_HANDLER_OK_FINALIZE_FAILED = "handler_ok_finalize_failed";

export function failedImportTaskStatusPrimaryLabel(status: string): string {
  switch (status) {
    case FAILED_IMPORT_STATUS_HANDLER_OK_FINALIZE_FAILED:
      return "Needs manual finish — work ran; completion not saved";
    case "failed":
      return "Stopped after errors";
    case "completed":
      return "Completed";
    case "pending":
      return "Waiting to start";
    case "leased":
      return "In progress";
    default:
      return status;
  }
}

export function isHandlerOkFinalizeFailedStatus(status: string): boolean {
  return status === FAILED_IMPORT_STATUS_HANDLER_OK_FINALIZE_FAILED;
}
