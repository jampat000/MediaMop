import { apiFetch, readJson, requireOk } from "../api/client";
import type { SystemReadiness } from "../api/types";

const systemReadinessPath = "/api/v1/system/readiness";

/**
 * Signed-in readiness: the installed version and whether the workers are running.
 *
 * The server answers 503 while it is starting or when a worker has stopped, with the same
 * body. That body is exactly what the shell wants to show, so a 503 is read, not thrown.
 */
export async function fetchSystemReadiness(): Promise<SystemReadiness> {
  const response = await apiFetch(systemReadinessPath);
  if (response.status !== 503) {
    await requireOk(
      systemReadinessPath,
      response,
      "Could not read whether MediaMop is running",
    );
  }
  return readJson<SystemReadiness>(response);
}
