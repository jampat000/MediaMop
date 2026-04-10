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

export type ActivityEventItem = {
  id: number;
  created_at: string;
  event_type: string;
  module: string;
  title: string;
  detail: string | null;
};

export type DashboardActivitySummary = {
  events_last_24h: number;
  latest: ActivityEventItem | null;
  last_fetcher_probe: ActivityEventItem | null;
};

export type DashboardStatus = {
  scope_note: string;
  system: DashboardSystemStatus;
  fetcher: DashboardFetcherStatus;
  activity_summary: DashboardActivitySummary;
};

export type FetcherProbePersistedWindow = {
  window_hours: number;
  persisted_ok: number;
  persisted_failed: number;
};

export type FetcherOperationalOverview = {
  mediamop_version: string;
  status_label: string;
  status_detail: string;
  connection: DashboardFetcherStatus;
  probe_persisted_24h: FetcherProbePersistedWindow;
  probe_failure_window_days: number;
  recent_probe_failures: ActivityEventItem[];
  latest_probe_event: ActivityEventItem | null;
  recent_probe_events: ActivityEventItem[];
};

export type ActivityRecentResponse = {
  items: ActivityEventItem[];
};
