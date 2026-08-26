import { fetchCsrfToken } from "../api/auth-api";
import { apiFetch, readJson, requireOk } from "../api/client";

/** A media manager MediaMop talks to. The kind selects the payload dialect, nothing more. */
export type MediaManagerKind = "radarr" | "sonarr" | "deluno" | "native";

export type SearchLane = "missing" | "upgrade";

export const MEDIA_MANAGER_KIND_LABELS: Record<MediaManagerKind, string> = {
  radarr: "Radarr",
  sonarr: "Sonarr",
  deluno: "Deluno",
  native: "Other (MediaMop payload)",
};

export interface MediaManagerSearchLane {
  lane: SearchLane;
  enabled: boolean;
  max_items_per_run: number;
  retry_delay_minutes: number;
  schedule_enabled: boolean;
  schedule_days: string;
  schedule_start: string;
  schedule_end: string;
  schedule_interval_seconds: number;
}

export interface MediaManagerConnection {
  id: number;
  kind: MediaManagerKind;
  name: string;
  enabled: boolean;
  base_url: string;
  api_key_is_saved: boolean;
  webhook_secret_is_set: boolean;
  webhook_url_path: string;
  last_test_ok: boolean | null;
  last_test_at: string | null;
  last_test_detail: string | null;
  lanes: MediaManagerSearchLane[];
}

export interface MediaManagerConnectionCreate {
  kind: MediaManagerKind;
  name: string;
  enabled: boolean;
  base_url: string;
  api_key: string;
}

export interface MediaManagerConnectionUpdate {
  name?: string;
  enabled?: boolean;
  base_url?: string;
  /** Omit to keep the saved key. Send "" to clear it. */
  api_key?: string;
}

export interface MediaManagerWebhookSecret {
  connection_id: number;
  webhook_secret: string;
  webhook_url_path: string;
  header_name: string;
}

export interface MediaManagerConnectionTest {
  connection_id: number;
  ok: boolean;
  detail: string;
  checked_at: string;
}

export const mediaManagerConnectionsPath = () =>
  "/api/v1/media-managers/connections";

const connectionPath = (id: number) => `${mediaManagerConnectionsPath()}/${id}`;

export async function fetchMediaManagerConnections(): Promise<
  MediaManagerConnection[]
> {
  const path = mediaManagerConnectionsPath();
  const r = await apiFetch(path);
  await requireOk(path, r, "Could not load media managers");
  return readJson<MediaManagerConnection[]>(r);
}

export async function createMediaManagerConnection(
  data: MediaManagerConnectionCreate,
): Promise<MediaManagerConnection> {
  const csrf_token = await fetchCsrfToken();
  const path = mediaManagerConnectionsPath();
  const r = await apiFetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ ...data, csrf_token }),
  });
  await requireOk(path, r, "Could not add that media manager");
  return readJson<MediaManagerConnection>(r);
}

export async function updateMediaManagerConnection(
  id: number,
  data: MediaManagerConnectionUpdate,
): Promise<MediaManagerConnection> {
  const csrf_token = await fetchCsrfToken();
  const path = connectionPath(id);
  const r = await apiFetch(path, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ ...data, csrf_token }),
  });
  await requireOk(path, r, "Could not save that media manager");
  return readJson<MediaManagerConnection>(r);
}

export async function deleteMediaManagerConnection(id: number): Promise<void> {
  const csrf_token = await fetchCsrfToken();
  const path = connectionPath(id);
  const r = await apiFetch(path, {
    method: "DELETE",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ csrf_token }),
  });
  await requireOk(path, r, "Could not remove that media manager");
}

export async function testMediaManagerConnection(
  id: number,
): Promise<MediaManagerConnectionTest> {
  const csrf_token = await fetchCsrfToken();
  const path = `${connectionPath(id)}/test`;
  const r = await apiFetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ csrf_token }),
  });
  await requireOk(path, r, "Could not test that media manager");
  return readJson<MediaManagerConnectionTest>(r);
}

export async function generateMediaManagerWebhookSecret(
  id: number,
): Promise<MediaManagerWebhookSecret> {
  const csrf_token = await fetchCsrfToken();
  const path = `${connectionPath(id)}/webhook-secret`;
  const r = await apiFetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ csrf_token }),
  });
  await requireOk(path, r, "Could not generate a webhook secret");
  return readJson<MediaManagerWebhookSecret>(r);
}
