import { REFINER_STATUS_HANDLER_OK_FINALIZE_FAILED } from "./refiner-job-status-labels";

/** Admin/operator only — show manual cleanup-drive enqueue controls. */
export function showManualCleanupDriveEnqueueControl(role: string | undefined): boolean {
  if (!role) {
    return false;
  }
  return role === "admin" || role === "operator";
}

/** Admin/operator only — viewers see inspection but cannot mutate. */
export function showRecoverFinalizeFailureControl(role: string | undefined, jobStatus: string): boolean {
  if (jobStatus !== REFINER_STATUS_HANDLER_OK_FINALIZE_FAILED) {
    return false;
  }
  if (!role) {
    return false;
  }
  return role === "admin" || role === "operator";
}
