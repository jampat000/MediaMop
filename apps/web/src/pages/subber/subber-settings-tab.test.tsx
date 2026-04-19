import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import * as authApi from "../../lib/api/auth-api";
import * as subberQueries from "../../lib/subber/subber-queries";
import { SubberSettingsTab } from "./subber-settings-tab";

function wrap(ui: ReactNode, client: QueryClient) {
  return (
    <QueryClientProvider client={client}>
      <MemoryRouter>{ui}</MemoryRouter>
    </QueryClientProvider>
  );
}

describe("SubberSettingsTab", () => {
  const mutateAsync = vi.fn().mockResolvedValue({});

  afterEach(() => {
    vi.restoreAllMocks();
  });

  beforeEach(() => {
    vi.spyOn(authApi, "fetchCsrfToken").mockResolvedValue("csrf");
    vi.spyOn(subberQueries, "useSubberSettingsQuery").mockReturnValue({
      data: {
        enabled: false,
        opensubtitles_username: "u",
        opensubtitles_password_set: true,
        opensubtitles_api_key_set: true,
        sonarr_base_url: "",
        sonarr_api_key_set: false,
        radarr_base_url: "",
        radarr_api_key_set: false,
        language_preferences: ["en"],
        subtitle_folder: "",
        tv_schedule_enabled: false,
        tv_schedule_interval_seconds: 3600,
        tv_schedule_hours_limited: false,
        tv_schedule_days: "",
        tv_schedule_start: "00:00",
        tv_schedule_end: "23:59",
        movies_schedule_enabled: false,
        movies_schedule_interval_seconds: 3600,
        movies_schedule_hours_limited: false,
        movies_schedule_days: "",
        movies_schedule_start: "00:00",
        movies_schedule_end: "23:59",
        tv_last_scheduled_scan_enqueued_at: null,
        movies_last_scheduled_scan_enqueued_at: null,
        fetcher_sonarr_base_url_hint: "",
        fetcher_radarr_base_url_hint: "",
        adaptive_searching_enabled: true,
        adaptive_searching_delay_hours: 168,
        adaptive_searching_max_attempts: 3,
        permanent_skip_after_attempts: 10,
        exclude_hearing_impaired: false,
        upgrade_enabled: false,
        upgrade_schedule_enabled: false,
        upgrade_schedule_interval_seconds: 604800,
        upgrade_schedule_hours_limited: false,
        upgrade_schedule_days: "",
        upgrade_schedule_start: "00:00",
        upgrade_schedule_end: "23:59",
        upgrade_last_scheduled_at: null,
        sonarr_path_mapping_enabled: false,
        sonarr_path_sonarr: "",
        sonarr_path_subber: "",
        radarr_path_mapping_enabled: false,
        radarr_path_radarr: "",
        radarr_path_subber: "",
      },
      isLoading: false,
      isError: false,
    } as unknown as ReturnType<typeof subberQueries.useSubberSettingsQuery>);
    vi.spyOn(subberQueries, "usePutSubberSettingsMutation").mockReturnValue({
      mutateAsync,
      isPending: false,
    } as unknown as ReturnType<typeof subberQueries.usePutSubberSettingsMutation>);
    vi.spyOn(subberQueries, "useSubberTestOpensubtitlesMutation").mockReturnValue({
      mutateAsync: vi.fn().mockResolvedValue({ ok: true, message: "ok" }),
      isPending: false,
    } as unknown as ReturnType<typeof subberQueries.useSubberTestOpensubtitlesMutation>);
    vi.spyOn(subberQueries, "useSubberTestSonarrMutation").mockReturnValue({
      mutate: vi.fn(),
      isPending: false,
    } as unknown as ReturnType<typeof subberQueries.useSubberTestSonarrMutation>);
    vi.spyOn(subberQueries, "useSubberTestRadarrMutation").mockReturnValue({
      mutate: vi.fn(),
      isPending: false,
    } as unknown as ReturnType<typeof subberQueries.useSubberTestRadarrMutation>);
    vi.spyOn(subberQueries, "useSubberLibrarySyncTvMutation").mockReturnValue({
      mutate: vi.fn(),
      mutateAsync: vi.fn().mockResolvedValue({ status: "queued" }),
      isPending: false,
    } as unknown as ReturnType<typeof subberQueries.useSubberLibrarySyncTvMutation>);
    vi.spyOn(subberQueries, "useSubberLibrarySyncMoviesMutation").mockReturnValue({
      mutate: vi.fn(),
      mutateAsync: vi.fn().mockResolvedValue({ status: "queued" }),
      isPending: false,
    } as unknown as ReturnType<typeof subberQueries.useSubberLibrarySyncMoviesMutation>);
    vi.spyOn(subberQueries, "useSubberProvidersQuery").mockReturnValue({
      data: [
        {
          provider_key: "opensubtitles_org",
          display_name: "OpenSubtitles.org",
          enabled: false,
          priority: 0,
          requires_account: true,
          has_credentials: false,
        },
      ],
      isLoading: false,
      isError: false,
    } as unknown as ReturnType<typeof subberQueries.useSubberProvidersQuery>);
    vi.spyOn(subberQueries, "usePutSubberProviderMutation").mockReturnValue({
      mutateAsync: vi.fn().mockResolvedValue({}),
      isPending: false,
    } as unknown as ReturnType<typeof subberQueries.usePutSubberProviderMutation>);
    vi.spyOn(subberQueries, "useSubberTestProviderMutation").mockReturnValue({
      mutateAsync: vi.fn().mockResolvedValue({ ok: true, message: "ok" }),
      isPending: false,
    } as unknown as ReturnType<typeof subberQueries.useSubberTestProviderMutation>);
  });

  it("saves OpenSubtitles when Save is clicked", async () => {
    const client = new QueryClient();
    render(wrap(<SubberSettingsTab canOperate />, client));
    await waitFor(() => expect(screen.getByTestId("subber-settings-tab")).toBeInTheDocument());
    fireEvent.click(screen.getByTestId("subber-save-opensubtitles"));
    await waitFor(() => expect(mutateAsync).toHaveBeenCalled());
  });

  it("renders subtitle providers section", async () => {
    const client = new QueryClient();
    render(wrap(<SubberSettingsTab canOperate />, client));
    await waitFor(() => expect(screen.getByTestId("subber-providers-section")).toBeInTheDocument());
  });

  it("runs test connection when Test is clicked", async () => {
    const testMut = vi.fn().mockResolvedValue({ ok: true, message: "Connected" });
    vi.spyOn(subberQueries, "useSubberTestOpensubtitlesMutation").mockReturnValue({
      mutateAsync: testMut,
      isPending: false,
    } as unknown as ReturnType<typeof subberQueries.useSubberTestOpensubtitlesMutation>);
    const client = new QueryClient();
    render(wrap(<SubberSettingsTab canOperate />, client));
    await waitFor(() => expect(screen.getByTestId("subber-test-opensubtitles")).toBeInTheDocument());
    fireEvent.click(screen.getByTestId("subber-test-opensubtitles"));
    await waitFor(() => expect(testMut).toHaveBeenCalled());
  });
});
