import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";
import type { UserPublic } from "../../lib/api/types";
import { qk } from "../../lib/auth/queries";
import { suiteSecurityOverviewQueryKey, suiteSettingsQueryKey } from "../../lib/suite/queries";
import type { SuiteSecurityOverviewOut, SuiteSettingsOut } from "../../lib/suite/types";
import { SettingsPage } from "./settings-page";

const operatorMe: UserPublic = { id: 1, username: "alice", role: "operator" };
const viewerMe: UserPublic = { id: 2, username: "bob", role: "viewer" };

const minimalSuiteSettings: SuiteSettingsOut = {
  product_display_name: "MediaMop",
  signed_in_home_notice: null,
  updated_at: "2026-04-11T00:00:00Z",
};

const minimalSecurity: SuiteSecurityOverviewOut = {
  session_signing_configured: true,
  sign_in_cookie_https_only: false,
  sign_in_cookie_same_site: "Lax (recommended for most setups)",
  extra_https_hardening_enabled: false,
  sign_in_attempt_limit: 30,
  sign_in_attempt_window_plain: "1 minute",
  first_time_setup_attempt_limit: 10,
  first_time_setup_attempt_window_plain: "1 hour",
  allowed_browser_origins_count: 1,
  restart_required_note:
    "These safety options are read when the app starts from the server configuration file. To change them, ask whoever runs the server to edit that file and restart the app.",
};

function wrap(ui: ReactNode, client: QueryClient) {
  return (
    <QueryClientProvider client={client}>
      <MemoryRouter>{ui}</MemoryRouter>
    </QueryClientProvider>
  );
}

function renderSettings(me: UserPublic) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  qc.setQueryData(suiteSettingsQueryKey, minimalSuiteSettings);
  qc.setQueryData(suiteSecurityOverviewQueryKey, minimalSecurity);
  qc.setQueryData(qk.me, me);
  return render(wrap(<SettingsPage />, qc));
}

describe("SettingsPage (suite settings)", () => {
  it("does not mention Sonarr or Radarr on the central Settings page", () => {
    const { container } = renderSettings(operatorMe);
    const t = (container.textContent ?? "").toLowerCase();
    expect(t).not.toContain("sonarr");
    expect(t).not.toContain("radarr");
    expect(screen.getByTestId("suite-settings-page")).toBeTruthy();
    expect(screen.getByTestId("suite-settings-global")).toBeTruthy();
  });

  it("hides save for viewers", () => {
    renderSettings(viewerMe);
    expect(screen.getByTestId("suite-settings-save")).toBeDisabled();
  });
});
