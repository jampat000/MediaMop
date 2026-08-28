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
      await screen.findByText(/Nothing is connected yet/i),
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

    // The card shows a full URL, not the bare path the API returns, because the
    // operator has to paste it into another app on another machine.
    const urls = screen
      .getAllByTestId("media-manager-webhook-url")
      .map((el) => el.textContent);
    expect(urls.some((u) => u?.endsWith("/api/v1/intake/webhook/deluno"))).toBe(
      true,
    );
    expect(urls.some((u) => u?.endsWith("/api/v1/intake/webhook/radarr"))).toBe(
      true,
    );
    expect(urls.every((u) => u?.startsWith("http"))).toBe(true);
  });

  it("warns when a manager has no secret, since anyone could post as it", async () => {
    vi.spyOn(api, "fetchMediaManagerConnections").mockResolvedValue([
      connection({ webhook_secret_is_set: false }),
    ]);
    render(<SettingsMediaManagersTab />, { wrapper });

    expect(await screen.findByText(/no secret yet/i)).toBeInTheDocument();
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
    expect(screen.getByText(/will not show it again/i)).toBeInTheDocument();
  });

  it("says Connected, not what the endpoint replied", async () => {
    vi.spyOn(api, "fetchMediaManagerConnections").mockResolvedValue([
      connection({
        last_test_ok: true,
        last_test_at: "2026-08-26T10:00:00Z",
        last_test_detail: "Connected. MediaMop can reach Deluno.",
      }),
    ]);
    render(<SettingsMediaManagersTab />, { wrapper });

    const status = await screen.findByTestId("media-manager-status");
    expect(status).toHaveTextContent("Connected");
    // The headline already says it. Repeating the backend's sentence underneath
    // would be the same fact twice.
    expect(status).not.toHaveTextContent("MediaMop can reach");
  });

  it("shows why a failed test failed, because that is the actionable part", async () => {
    vi.spyOn(api, "fetchMediaManagerConnections").mockResolvedValue([
      connection({
        last_test_ok: false,
        last_test_at: "2026-08-26T10:00:00Z",
        last_test_detail:
          "MediaMop reached Deluno, but the API key was refused. Check the key and save it again.",
      }),
    ]);
    render(<SettingsMediaManagersTab />, { wrapper });

    const status = await screen.findByTestId("media-manager-status");
    expect(status).toHaveTextContent("Connection failed");
    expect(status).toHaveTextContent(/API key was refused/i);
  });

  it("says it has not been checked rather than implying a result", async () => {
    vi.spyOn(api, "fetchMediaManagerConnections").mockResolvedValue([
      connection({ last_test_ok: null, last_test_at: null }),
    ]);
    render(<SettingsMediaManagersTab />, { wrapper });

    const status = await screen.findByTestId("media-manager-status");
    expect(status).toHaveTextContent("Not checked yet");
    expect(status).toHaveTextContent("never");
  });

  it("keeps the address and secret folded away behind a disclosure", async () => {
    vi.spyOn(api, "fetchMediaManagerConnections").mockResolvedValue([
      connection(),
    ]);
    render(<SettingsMediaManagersTab />, { wrapper });

    // The card answers "is it connected" first; wiring details are one click away.
    const details = await screen.findByTestId("media-manager-setup-details");
    expect(details.tagName.toLowerCase()).toBe("details");
    expect(details).not.toHaveAttribute("open");
  });

  it("does not name internal modules in the intro", async () => {
    vi.spyOn(api, "fetchMediaManagerConnections").mockResolvedValue([]);
    const { container } = render(<SettingsMediaManagersTab />, { wrapper });
    await screen.findByText(/Nothing is connected yet/i);

    // The intro used to explain Radarr, Sonarr, Deluno and Refiner in one
    // breath. None of that helps someone deciding what this screen is for.
    const text = container.textContent ?? "";
    for (const word of ["Refiner", "Pruner"]) {
      expect(text).not.toContain(word);
    }
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
