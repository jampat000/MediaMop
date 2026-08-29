import { fetchCsrfToken } from "../api/auth-api";
import { apiFetch, readJson, requireOk } from "../api/client";

export interface SuitePause {
  paused: boolean;
  /** When the pause lifts on its own. Null for one that lasts until it is lifted by hand. */
  paused_until: string | null;
  scan_while_paused: boolean;
  reason: string;
  /** What happens to work already running. Shown, not assumed. */
  in_flight_policy: string;
}

export interface SuitePauseWrite {
  paused: boolean;
  pause_for_minutes?: number | null;
  scan_while_paused: boolean;
}

export const suitePausePath = () => "/api/v1/suite/pause";

export async function fetchSuitePause(): Promise<SuitePause> {
  const path = suitePausePath();
  const response = await apiFetch(path);
  await requireOk(
    path,
    response,
    "Could not read whether processing is paused",
  );
  return readJson<SuitePause>(response);
}

export async function saveSuitePause(
  body: SuitePauseWrite,
): Promise<SuitePause> {
  const csrf_token = await fetchCsrfToken();
  const path = suitePausePath();
  const response = await apiFetch(path, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ ...body, csrf_token }),
  });
  await requireOk(
    path,
    response,
    "Could not change whether processing is paused",
  );
  return readJson<SuitePause>(response);
}
