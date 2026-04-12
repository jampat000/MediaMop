"""HTTP shapes for suite-wide settings and the read-only security overview."""

from __future__ import annotations

from datetime import datetime

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
    updated_at: datetime


class SuiteSettingsPutIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    csrf_token: str = Field(..., min_length=1)
    product_display_name: str = Field(..., min_length=1, max_length=120)
    signed_in_home_notice: str | None = Field(default=None, max_length=4000)


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
