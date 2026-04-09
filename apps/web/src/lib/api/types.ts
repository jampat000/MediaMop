export type UserPublic = {
  id: number;
  username: string;
  role: string;
};

export type BootstrapStatus = {
  bootstrap_allowed: boolean;
  reason: string;
};

export type DashboardSystemStatus = {
  api_version: string;
  environment: string;
  healthy: boolean;
};

export type DashboardFetcherStatus = {
  configured: boolean;
  target_display: string | null;
  reachable: boolean | null;
  http_status: number | null;
  latency_ms: number | null;
  fetcher_app: string | null;
  fetcher_version: string | null;
  detail: string | null;
};

export type DashboardStatus = {
  scope_note: string;
  system: DashboardSystemStatus;
  fetcher: DashboardFetcherStatus;
};
