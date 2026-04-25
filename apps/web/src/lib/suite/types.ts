/** GET/PUT /api/v1/suite/settings — names and notices stored in the app database. */

export type SuiteSettingsOut = {
  product_display_name: string;
  signed_in_home_notice: string | null;
  setup_wizard_state: "pending" | "skipped" | "completed" | string;
  app_timezone: string;
  log_retention_days: number;
  configuration_backup_enabled?: boolean;
  configuration_backup_interval_hours?: number;
  configuration_backup_preferred_time?: string;
  configuration_backup_last_run_at?: string | null;
  updated_at: string;
};

export type SuiteSettingsPutBody = {
  product_display_name: string;
  signed_in_home_notice: string | null;
  setup_wizard_state?: "pending" | "skipped" | "completed" | string;
  app_timezone: string;
  log_retention_days: number;
  /** Older APIs required this flag; current servers ignore it. Always send `true` when saving suite settings. */
  application_logs_enabled: boolean;
  configuration_backup_enabled?: boolean;
  configuration_backup_interval_hours?: number;
  configuration_backup_preferred_time?: string;
};

/** GET /api/v1/suite/security-overview — read-only snapshot from server startup configuration. */

export type SuiteSecurityOverviewOut = {
  session_signing_configured: boolean;
  sign_in_cookie_https_only: boolean;
  sign_in_cookie_same_site: string;
  extra_https_hardening_enabled: boolean;
  sign_in_attempt_limit: number;
  sign_in_attempt_window_plain: string;
  first_time_setup_attempt_limit: number;
  first_time_setup_attempt_window_plain: string;
  allowed_browser_origins_count: number;
  restart_required_note: string;
};

export type SuiteConfigurationBackupItem = {
  id: number;
  created_at: string;
  file_name: string;
  size_bytes: number;
};

export type SuiteConfigurationBackupListOut = {
  directory: string;
  items: SuiteConfigurationBackupItem[];
};

export type SuiteUpdateStatusOut = {
  current_version: string;
  install_type: string;
  status: "up_to_date" | "update_available" | "unavailable" | string;
  summary: string;
  latest_version?: string | null;
  latest_name?: string | null;
  published_at?: string | null;
  release_url?: string | null;
  windows_installer_url?: string | null;
  docker_image?: string | null;
  docker_tag?: string | null;
  docker_update_command?: string | null;
};

export type SuiteUpdateStartOut = {
  status: "started" | "unavailable" | string;
  message: string;
  target_version?: string | null;
};

export type SuiteLogEntry = {
  timestamp: string;
  level: string;
  component: string;
  message: string;
  detail?: string | null;
  traceback?: string | null;
  source?: string | null;
  logger: string;
  correlation_id?: string | null;
  job_id?: string | null;
};

export type SuiteLogsOut = {
  items: SuiteLogEntry[];
  total: number;
  counts: {
    error: number;
    warning: number;
    information: number;
  };
};

export type SuiteMetricsRoute = {
  route: string;
  request_count: number;
  average_response_ms: number;
};

export type SuiteMetricsOut = {
  uptime_seconds: number;
  total_requests: number;
  average_response_ms: number;
  error_log_count: number;
  status_counts: Record<string, number>;
  busiest_routes: SuiteMetricsRoute[];
};

export function suiteSettingsBackupFieldsPresent(v: SuiteSettingsOut): boolean {
  return (
    typeof v.configuration_backup_enabled === "boolean" &&
    typeof v.configuration_backup_interval_hours === "number" &&
    typeof v.configuration_backup_preferred_time === "string"
  );
}
