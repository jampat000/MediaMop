import { fetchCsrfToken } from "../api/auth-api";
import { apiErrorDetailToString, apiFetch, readJson } from "../api/client";

export type BrokerIndexer = {
  id: number;
  name: string;
  slug: string;
  kind: string;
  protocol: string;
  privacy: string;
  url: string;
  api_key: string;
  enabled: boolean;
  priority: number;
  categories: number[];
  tags: string[];
  last_tested_at: string | null;
  last_test_ok: boolean | null;
  last_test_error: string | null;
  created_at: string;
  updated_at: string;
};

export type BrokerArrConnection = {
  id: number;
  arr_type: string;
  url: string;
  api_key: string;
  sync_mode: string;
  last_synced_at: string | null;
  last_sync_ok: boolean | null;
  last_sync_error: string | null;
  last_manual_sync_at: string | null;
  last_manual_sync_ok: boolean | null;
  indexer_fingerprint: string | null;
  created_at: string;
  updated_at: string;
};

export type BrokerResult = {
  title: string;
  url: string;
  magnet: string | null;
  size: number;
  seeders: number | null;
  leechers: number | null;
  protocol: string;
  indexer_slug: string;
  categories: number[];
  published_at: string | null;
  imdb_id: string | null;
  info_hash: string | null;
};

export type BrokerJob = {
  id: number;
  job_kind: string;
  status: string;
  attempt_count: number;
  last_error: string | null;
  created_at: string;
  updated_at: string;
};

export type BrokerSettings = {
  proxy_api_key: string;
};

export type BrokerIndexerCreateIn = {
  name: string;
  slug: string;
  kind: string;
  protocol: string;
  privacy?: string;
  url?: string;
  api_key?: string;
  enabled: boolean;
  priority: number;
  categories: number[];
  tags: string[];
};

export type BrokerIndexerUpdateIn = {
  name?: string;
  slug?: string;
  kind?: string;
  protocol?: string;
  privacy?: string;
  url?: string;
  api_key?: string;
  enabled?: boolean;
  priority?: number;
  categories?: number[];
  tags?: string[];
};

export type BrokerConnectionUpdateIn = {
  url?: string;
  api_key?: string;
  sync_mode?: string;
};

async function throwUnlessOk(r: Response, fallback: string): Promise<void> {
  if (r.ok) {
    return;
  }
  let msg = fallback;
  try {
    const body = await readJson<{ detail?: unknown }>(r);
    const d = apiErrorDetailToString(body.detail);
    if (d) {
      msg = d;
    }
  } catch {
    /* ignore */
  }
  throw new Error(msg || `${fallback} (${r.status})`);
}

export async function getBrokerIndexers(): Promise<BrokerIndexer[]> {
  const r = await apiFetch("/api/v1/broker/indexers");
  if (!r.ok) {
    throw new Error(`Could not load Broker indexers (${r.status})`);
  }
  return readJson<BrokerIndexer[]>(r);
}

export async function createBrokerIndexer(data: BrokerIndexerCreateIn): Promise<BrokerIndexer> {
  const csrf_token = await fetchCsrfToken();
  const r = await apiFetch("/api/v1/broker/indexers", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ ...data, csrf_token }),
  });
  await throwUnlessOk(r, "Could not create indexer");
  return readJson<BrokerIndexer>(r);
}

export async function updateBrokerIndexer(id: number, data: BrokerIndexerUpdateIn): Promise<BrokerIndexer> {
  const csrf_token = await fetchCsrfToken();
  const r = await apiFetch(`/api/v1/broker/indexers/${id}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ ...data, csrf_token }),
  });
  await throwUnlessOk(r, "Could not update indexer");
  return readJson<BrokerIndexer>(r);
}

export async function deleteBrokerIndexer(id: number): Promise<void> {
  const r = await apiFetch(`/api/v1/broker/indexers/${id}`, { method: "DELETE" });
  if (r.status === 204) {
    return;
  }
  await throwUnlessOk(r, "Could not delete indexer");
}

export async function testBrokerIndexer(id: number): Promise<void> {
  const csrf_token = await fetchCsrfToken();
  const r = await apiFetch(`/api/v1/broker/indexers/${id}/test`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ csrf_token }),
  });
  await throwUnlessOk(r, "Could not enqueue indexer test");
}

export async function getBrokerConnection(arrType: string): Promise<BrokerArrConnection> {
  const at = arrType.trim().toLowerCase();
  const r = await apiFetch(`/api/v1/broker/connections/${encodeURIComponent(at)}`);
  if (!r.ok) {
    throw new Error(`Could not load ${at} connection (${r.status})`);
  }
  return readJson<BrokerArrConnection>(r);
}

export async function updateBrokerConnection(
  arrType: string,
  data: BrokerConnectionUpdateIn,
): Promise<BrokerArrConnection> {
  const csrf_token = await fetchCsrfToken();
  const at = arrType.trim().toLowerCase();
  const r = await apiFetch(`/api/v1/broker/connections/${encodeURIComponent(at)}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ ...data, csrf_token }),
  });
  await throwUnlessOk(r, "Could not save connection");
  return readJson<BrokerArrConnection>(r);
}

export async function syncBrokerConnection(arrType: string): Promise<void> {
  const csrf_token = await fetchCsrfToken();
  const at = arrType.trim().toLowerCase();
  const r = await apiFetch(`/api/v1/broker/connections/${encodeURIComponent(at)}/sync`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ csrf_token }),
  });
  await throwUnlessOk(r, "Could not enqueue sync");
}

export async function brokerSearch(params: {
  q: string;
  type?: string;
  indexers?: string;
  limit?: number;
}): Promise<BrokerResult[]> {
  const sp = new URLSearchParams();
  sp.set("q", params.q.trim());
  if (params.type) {
    sp.set("type", params.type);
  }
  if (params.indexers !== undefined && params.indexers !== "") {
    sp.set("indexers", params.indexers);
  }
  if (params.limit != null) {
    sp.set("limit", String(params.limit));
  }
  const r = await apiFetch(`/api/v1/broker/search?${sp.toString()}`);
  if (!r.ok) {
    throw new Error(`Broker search failed (${r.status})`);
  }
  return readJson<BrokerResult[]>(r);
}

type BrokerJobsInspectionOut = {
  jobs: BrokerJob[];
  default_recent_slice: boolean;
};

export async function getBrokerJobs(): Promise<BrokerJob[]> {
  const r = await apiFetch("/api/v1/broker/jobs?limit=100");
  if (!r.ok) {
    throw new Error(`Could not load Broker jobs (${r.status})`);
  }
  const body = await readJson<BrokerJobsInspectionOut>(r);
  return body.jobs ?? [];
}

export async function getBrokerSettings(): Promise<BrokerSettings> {
  const r = await apiFetch("/api/v1/broker/proxy/apikey");
  if (!r.ok) {
    throw new Error(`Could not load Broker proxy settings (${r.status})`);
  }
  return readJson<BrokerSettings>(r);
}

export async function rotateBrokerProxyKey(): Promise<BrokerSettings> {
  const csrf_token = await fetchCsrfToken();
  const r = await apiFetch("/api/v1/broker/proxy/apikey/rotate", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ csrf_token }),
  });
  await throwUnlessOk(r, "Could not rotate proxy API key");
  return readJson<BrokerSettings>(r);
}
