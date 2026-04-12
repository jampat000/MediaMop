/** GET/PUT /api/v1/suite/settings — names and notices stored in the app database. */

export type SuiteSettingsOut = {
  product_display_name: string;
  signed_in_home_notice: string | null;
  updated_at: string;
};

export type SuiteSettingsPutBody = {
  product_display_name: string;
  signed_in_home_notice: string | null;
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
