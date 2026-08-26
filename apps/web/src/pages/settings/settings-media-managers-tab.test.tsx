import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import * as api from "../../lib/media-managers/media-managers-api";
import type { MediaManagerConnection } from "../../lib/media-managers/media-managers-api";
import { SettingsMediaManagersTab } from "./settings-media-managers-tab";

function connection(
  over: Partial<MediaManagerConnection> = {},
): MediaManagerConnection {
  return {
    id: 1,
    kind: "deluno",
    name: "Deluno",
    enabled: true,
    base_url: "http://10.1.1.142:5099",
    api_key_is_saved: true,
    webhook_secret_is_set: false,
    webhook_url_path: "/api/v1/intake/webhook/deluno",
    last_test_ok: null,
    last_test_at: null,
    last_test_detail: null,
    lanes: [],
    ...over,
  };
}

function wrapper({ children }: { children: ReactNode }) {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe("SettingsMediaManagersTab", () => {
  it("says plainly when nothing is configured, because nothing will reach MediaMop", async () => {
    vi.spyOn(api, "fetchMediaManagerConnections").mockResolvedValue([]);
    render(<SettingsMediaManagersTab />, { wrapper });

    expect(
      await screen.findByText(/No media managers yet/i),
    ).toBeInTheDocument();
  });

  it("shows each manager with the address it should post to", async () => {
    vi.spyOn(api, "fetchMediaManagerConnections").mockResolvedValue([
      connection(),
      connection({
        id: 2,
        kind: "radarr",
        name: "Radarr",
        webhook_url_path: "/api/v1/intake/webhook/radarr",
      }),
    ]);
    render(<SettingsMediaManagersTab />, { wrapper });

    expect(await screen.findByText("Deluno")).toBeInTheDocument();
    expect(screen.getByText("Radarr")).toBeInTheDocument();
    expect(
      screen.getByText("/api/v1/intake/webhook/deluno"),
    ).toBeInTheDocument();
    expect(
      screen.getByText("/api/v1/intake/webhook/radarr"),
    ).toBeInTheDocument();
  });

  it("warns when a manager has no secret, since anyone could post as it", async () => {
    vi.spyOn(api, "fetchMediaManagerConnections").mockResolvedValue([
      connection({ webhook_secret_is_set: false }),
    ]);
    render(<SettingsMediaManagersTab />, { wrapper });

    expect(await screen.findByText(/No secret set/i)).toBeInTheDocument();
  });

  it("shows a generated secret once, and says that is the only time", async () => {
    vi.spyOn(api, "fetchMediaManagerConnections").mockResolvedValue([
      connection(),
    ]);
    vi.spyOn(api, "generateMediaManagerWebhookSecret").mockResolvedValue({
      connection_id: 1,
      webhook_secret: "s3cr3t-value",
      webhook_url_path: "/api/v1/intake/webhook/deluno",
      header_name: "X-Webhook-Secret",
    });

    render(<SettingsMediaManagersTab />, { wrapper });
    fireEvent.click(await screen.findByTestId("media-manager-generate-secret"));

    await waitFor(() =>
      expect(screen.getByTestId("media-manager-secret")).toHaveTextContent(
        "s3cr3t-value",
      ),
    );
    expect(screen.getByText(/only time it is shown/i)).toBeInTheDocument();
  });

  it("reports a failed connection test in the words the API used", async () => {
    vi.spyOn(api, "fetchMediaManagerConnections").mockResolvedValue([
      connection({
        last_test_ok: false,
        last_test_detail:
          "http://10.1.1.142:5099 is reachable but rejected the API key.",
      }),
    ]);
    render(<SettingsMediaManagersTab />, { wrapper });

    expect(
      await screen.findByText(/rejected the API key/i),
    ).toBeInTheDocument();
  });

  it("adds a manager of a kind that never had columns of its own", async () => {
    vi.spyOn(api, "fetchMediaManagerConnections").mockResolvedValue([]);
    const create = vi
      .spyOn(api, "createMediaManagerConnection")
      .mockResolvedValue(connection());

    render(<SettingsMediaManagersTab />, { wrapper });
    fireEvent.click(await screen.findByTestId("media-manager-add"));

    fireEvent.change(screen.getByTestId("media-manager-name"), {
      target: { value: "Deluno" },
    });
    fireEvent.change(screen.getByTestId("media-manager-base-url"), {
      target: { value: "http://10.1.1.142:5099" },
    });
    fireEvent.click(screen.getByTestId("media-manager-save"));

    await waitFor(() =>
      expect(create).toHaveBeenCalledWith(
        expect.objectContaining({
          kind: "deluno",
          name: "Deluno",
          base_url: "http://10.1.1.142:5099",
        }),
      ),
    );
  });

  it("will not submit a manager with no name", async () => {
    vi.spyOn(api, "fetchMediaManagerConnections").mockResolvedValue([]);
    render(<SettingsMediaManagersTab />, { wrapper });
    fireEvent.click(await screen.findByTestId("media-manager-add"));

    expect(screen.getByTestId("media-manager-save")).toBeDisabled();
  });
});
