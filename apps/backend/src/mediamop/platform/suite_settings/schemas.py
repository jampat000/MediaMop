"""HTTP shapes for suite-wide settings and the read-only security overview."""

from __future__ import annotations

from datetime import datetime

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class SuiteSettingsOut(BaseModel):
    """Values stored in ``suite_settings`` (editable in the app)."""

    model_config = ConfigDict(extra="forbid")

    product_display_name: str = Field(max_length=120, description="Shown in the sidebar and settings.")
    signed_in_home_notice: str | None = Field(
        default=None,
        max_length=4000,
        description="Optional short message on the home dashboard for signed-in users.",
    )
    setup_wizard_state: str = Field(
        min_length=1,
        max_length=32,
        description="First-run wizard state: pending, skipped, or completed.",
    )
    app_timezone: str = Field(
        max_length=120,
        description="Suite-wide timezone label used for date/time displays that follow app timezone.",
    )
    log_retention_days: int = Field(
        ge=1,
        le=3650,
        description="How long persisted system logs are kept before automatic cleanup.",
    )
    configuration_backup_enabled: bool = Field(
        description="Whether server-side automatic configuration snapshots are enabled.",
    )
    configuration_backup_interval_hours: int = Field(
        ge=1,
        le=720,
        description="Minimum hours between automatic configuration snapshots.",
    )
    configuration_backup_preferred_time: str = Field(
        min_length=5,
        max_length=5,
        description="Preferred local backup time in HH:MM for daily-style automatic snapshots.",
    )
    configuration_backup_last_run_at: datetime | None = Field(
        default=None,
        description="UTC timestamp of the last successful automatic configuration snapshot run.",
    )
    updated_at: datetime


class SuiteSettingsPutIn(BaseModel):
    """Body for ``PUT /suite/settings``.

    ``extra="ignore"`` keeps older browser builds or tools from failing when they send removed keys.
    ``application_logs_enabled`` is accepted for compatibility with pre-0047 APIs but is not persisted.
    """

    model_config = ConfigDict(extra="ignore")

    csrf_token: str = Field(..., min_length=1)
    product_display_name: str = Field(..., min_length=1, max_length=120)
    signed_in_home_notice: str | None = Field(default=None, max_length=4000)
    setup_wizard_state: str | None = Field(default=None, min_length=1, max_length=32)
    app_timezone: str = Field(..., min_length=1, max_length=120)
    log_retention_days: int = Field(ge=1, le=3650)
    application_logs_enabled: bool | None = Field(
        default=None,
        description="Deprecated; retained so older clients can POST without changes. Ignored when persisting.",
    )
    configuration_backup_enabled: bool | None = Field(
        default=None,
        description="Enable or disable periodic automatic configuration snapshots.",
    )
    configuration_backup_interval_hours: int | None = Field(
        default=None,
        ge=1,
        le=720,
        description="Minimum hours between automatic configuration snapshots.",
    )
    configuration_backup_preferred_time: str | None = Field(
        default=None,
        min_length=5,
        max_length=5,
        description="Preferred local backup time in HH:MM for daily-style automatic snapshots.",
    )


class ConfigurationBundleImportIn(BaseModel):
    """Restore suite + module settings from a prior configuration bundle export."""

    model_config = ConfigDict(extra="forbid")

    csrf_token: str = Field(..., min_length=1)
    bundle: dict[str, Any]


class SuiteConfigurationBackupItemOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    created_at: datetime
    file_name: str
    size_bytes: int


class SuiteConfigurationBackupListOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    directory: str
    items: list[SuiteConfigurationBackupItemOut]


class SuiteSecurityOverviewOut(BaseModel):
    """Read-only snapshot from startup configuration — not stored in ``suite_settings``."""

    model_config = ConfigDict(extra="forbid")

    session_signing_configured: bool = Field(
        description="Whether the app was started with a sign-in signing key configured.",
    )
    sign_in_cookie_https_only: bool = Field(description="Whether the sign-in cookie is marked for HTTPS only.")
    sign_in_cookie_same_site: str = Field(description="How strictly the browser limits the sign-in cookie.")
    extra_https_hardening_enabled: bool = Field(
        description="Whether strict transport (HSTS) extra protection is enabled for browser responses.",
    )
    sign_in_attempt_limit: int = Field(ge=1, description="How many failed sign-in tries are allowed before cooling off.")
    sign_in_attempt_window_plain: str = Field(
        description="How long the sign-in try window lasts, in everyday wording.",
    )
    first_time_setup_attempt_limit: int = Field(
        ge=1,
        description="How many first-time setup tries are allowed before cooling off.",
    )
    first_time_setup_attempt_window_plain: str = Field(
        description="How long the first-time setup try window lasts, in everyday wording.",
    )
    allowed_browser_origins_count: int = Field(
        ge=0,
        description="How many website addresses may call this app from a browser.",
    )
    restart_required_note: str = Field(
        description="Plain explanation that these values follow the server configuration file and a restart.",
    )


class SuiteUpdateStatusOut(BaseModel):
    """Current app version compared with the latest public release."""

    model_config = ConfigDict(extra="forbid")

    current_version: str = Field(min_length=1)
    install_type: str = Field(min_length=1, description="windows, docker, or source")
    status: str = Field(min_length=1, description="up_to_date, update_available, or unavailable")
    summary: str = Field(min_length=1)
    latest_version: str | None = None
    latest_name: str | None = None
    published_at: datetime | None = None
    release_url: str | None = None
    windows_installer_url: str | None = None
    docker_image: str | None = None
    docker_tag: str | None = None
    docker_update_command: str | None = None


class SuiteUpdateStartOut(BaseModel):
    """Result of requesting an in-place app upgrade."""

    model_config = ConfigDict(extra="forbid")

    status: str = Field(min_length=1, description="started or unavailable")
    message: str = Field(min_length=1)
    target_version: str | None = None


class SuiteUpdateStartIn(BaseModel):
    """Body for ``POST /suite/update-now``."""

    model_config = ConfigDict(extra="forbid")

    csrf_token: str = Field(..., min_length=1)


class SuiteLogEntryOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    timestamp: datetime
    level: str
    component: str
    message: str
    detail: str | None = None
    traceback: str | None = None
    source: str | None = None
    logger: str
    correlation_id: str | None = None
    job_id: str | None = None


class SuiteLogCountsOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    error: int
    warning: int
    information: int


class SuiteLogsOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[SuiteLogEntryOut]
    total: int
    counts: SuiteLogCountsOut


class SuiteMetricsRouteOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    route: str
    request_count: int
    average_response_ms: float


class SuiteMetricsOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    uptime_seconds: float
    total_requests: int
    average_response_ms: float
    error_log_count: int
    status_counts: dict[str, int]
    busiest_routes: list[SuiteMetricsRouteOut]
