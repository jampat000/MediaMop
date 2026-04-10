import { FAILED_IMPORT_STATUS_HANDLER_OK_FINALIZE_FAILED } from "./task-status-labels";

/** Admin/operator — show manual enqueue for Radarr/Sonarr failed-import passes. */
export function showFailedImportManualEnqueueControl(role: string | undefined): boolean {
  if (!role) {
    return false;
  }
  return role === "admin" || role === "operator";
}

/** Admin/operator — manual recover for needs-manual-finish tasks only. */
export function showFailedImportRecoverControl(role: string | undefined, jobStatus: string): boolean {
  if (jobStatus !== FAILED_IMPORT_STATUS_HANDLER_OK_FINALIZE_FAILED) {
    return false;
  }
  if (!role) {
    return false;
  }
  return role === "admin" || role === "operator";
}
