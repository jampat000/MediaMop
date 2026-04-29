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
  worker_health?: Array<{
    module: string;
    expected_workers: number;
    active_workers: number;
    stale_workers: number;
    stopped_workers: number;
    status: string;
    detail: string;
  }>;
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
};

export type DashboardStatus = {
  scope_note: string;
  system: DashboardSystemStatus;
  activity_summary: DashboardActivitySummary;
};

export type ActivityRecentResponse = {
  items: ActivityEventItem[];
  total: number;
  system_events: number;
};
