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
    base_url: "http://192.0.2.10:5099",
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
  it("says plainly when nothing is configured, because nothing will reach Weir", async () => {
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
        last_test_detail: "Connected. Weir can reach Deluno.",
      }),
    ]);
    render(<SettingsMediaManagersTab />, { wrapper });

    const status = await screen.findByTestId("media-manager-status");
    expect(status).toHaveTextContent("Connected");
    // The headline already says it. Repeating the backend's sentence underneath
    // would be the same fact twice.
    expect(status).not.toHaveTextContent("Weir can reach");
  });

  it("shows why a failed test failed, because that is the actionable part", async () => {
    vi.spyOn(api, "fetchMediaManagerConnections").mockResolvedValue([
      connection({
        last_test_ok: false,
        last_test_at: "2026-08-26T10:00:00Z",
        last_test_detail:
          "Weir reached Deluno, but the API key was refused. Check the key and save it again.",
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

  it("never says Connected when there is no check time behind it", async () => {
    vi.spyOn(api, "fetchMediaManagerConnections").mockResolvedValue([
      connection({
        last_test_ok: true,
        last_test_at: null,
        last_test_detail: "Reachable, 214 series",
      }),
    ]);
    render(<SettingsMediaManagersTab />, { wrapper });

    const status = await screen.findByTestId("media-manager-status");
    // "Connected" above "Last checked: never" is two statements that cannot both
    // be true. Without a time, nothing has established the connection.
    expect(status).not.toHaveTextContent("Connected");
    expect(status).toHaveTextContent("Not checked yet");
    expect(status).toHaveTextContent("never");
    expect(status.querySelector(".mm-status-text--healthy")).toBeNull();
  });

  it("prevents remove or update while a connection test is running", async () => {
    vi.spyOn(api, "fetchMediaManagerConnections").mockResolvedValue([
      connection(),
    ]);
    let finishTest!: (value: api.MediaManagerConnectionTest) => void;
    const pendingTest = new Promise<api.MediaManagerConnectionTest>(
      (resolve) => {
        finishTest = resolve;
      },
    );
    vi.spyOn(api, "testMediaManagerConnection").mockReturnValue(pendingTest);

    render(<SettingsMediaManagersTab />, { wrapper });
    fireEvent.click(await screen.findByTestId("media-manager-test"));

    await waitFor(() =>
      expect(screen.getByTestId("media-manager-test")).toBeDisabled(),
    );
    expect(screen.getByTestId("media-manager-remove")).toBeDisabled();
    expect(screen.getByRole("button", { name: "Disable" })).toBeDisabled();

    finishTest({
      connection_id: 1,
      ok: false,
      detail: "Could not reach Deluno.",
      checked_at: "2026-09-01T07:00:00Z",
    });
    await waitFor(() =>
      expect(screen.getByTestId("media-manager-remove")).toBeEnabled(),
    );
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
    // The summary says it opens, since the browser's own triangle is hidden.
    const summary = details.querySelector("summary");
    expect(summary).toHaveTextContent("How to point Deluno at Weir");
    expect(summary).toHaveTextContent("Show →");
  });

  it("points Sonarr and Radarr at the library editor's mapping, not at Deluno's hand-off", async () => {
    vi.spyOn(api, "fetchMediaManagerConnections").mockResolvedValue([
      connection({ id: 2, kind: "sonarr", name: "Sonarr" }),
      connection(),
    ]);
    render(<SettingsMediaManagersTab />, { wrapper });

    const pointer = await screen.findByTestId("media-manager-mapping-pointer");
    expect(pointer).toHaveTextContent(
      "Sonarr picks up what Weir cleans through a remote path mapping",
    );
    expect(screen.getAllByTestId("media-manager-mapping-pointer")).toHaveLength(
      1,
    );
  });

  it("does not name internal modules in the intro", async () => {
    vi.spyOn(api, "fetchMediaManagerConnections").mockResolvedValue([]);
    const { container } = render(<SettingsMediaManagersTab />, { wrapper });
    await screen.findByText(/Nothing is connected yet/i);

    // The intro used to explain Radarr, Sonarr, Deluno and Processing in one
    // breath. None of that helps someone deciding what this screen is for.
    const text = container.textContent ?? "";
    expect(text).not.toContain("Processing");
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
      target: { value: "http://192.0.2.10:5099" },
    });
    fireEvent.click(screen.getByTestId("media-manager-save"));

    await waitFor(() =>
      expect(create).toHaveBeenCalledWith(
        expect.objectContaining({
          kind: "deluno",
          name: "Deluno",
          base_url: "http://192.0.2.10:5099",
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

  // #599 follow-up: Remove used to delete on the first click. What matters is not that a
  // dialog appears — it is that nothing is deleted until the dialog is confirmed.
  describe("removing a connection", () => {
    function threeConnections() {
      return [
        connection({ id: 1, name: "Deluno" }),
        connection({ id: 2, kind: "radarr", name: "Radarr" }),
        connection({ id: 3, kind: "sonarr", name: "Sonarr" }),
      ];
    }

    it("does not delete anything on the first click", async () => {
      vi.spyOn(api, "fetchMediaManagerConnections").mockResolvedValue(
        threeConnections(),
      );
      const del = vi
        .spyOn(api, "deleteMediaManagerConnection")
        .mockResolvedValue(undefined);

      render(<SettingsMediaManagersTab />, { wrapper });
      fireEvent.click(
        (await screen.findAllByTestId("media-manager-remove"))[1],
      );

      expect(
        await screen.findByTestId("media-manager-remove-confirm"),
      ).toBeInTheDocument();
      expect(del).not.toHaveBeenCalled();
      // And the connection is still on screen behind the dialog.
      expect(screen.getByText("Radarr")).toBeInTheDocument();
    });

    it("names the connection it is about to remove, not just 'this one'", async () => {
      vi.spyOn(api, "fetchMediaManagerConnections").mockResolvedValue(
        threeConnections(),
      );
      render(<SettingsMediaManagersTab />, { wrapper });

      // Second of three: the case where an unnamed prompt would be useless.
      fireEvent.click(
        (await screen.findAllByTestId("media-manager-remove"))[1],
      );

      const dialog = screen.getByTestId("media-manager-remove-confirm");
      expect(dialog).toHaveTextContent("Remove Radarr?");
      expect(dialog).not.toHaveTextContent("Remove Deluno?");
      expect(dialog).not.toHaveTextContent("Remove Sonarr?");
    });

    it("leaves the connection alone when the dialog is cancelled", async () => {
      vi.spyOn(api, "fetchMediaManagerConnections").mockResolvedValue(
        threeConnections(),
      );
      const del = vi
        .spyOn(api, "deleteMediaManagerConnection")
        .mockResolvedValue(undefined);

      render(<SettingsMediaManagersTab />, { wrapper });
      fireEvent.click(
        (await screen.findAllByTestId("media-manager-remove"))[1],
      );
      fireEvent.click(
        screen.getByTestId("media-manager-remove-confirm-cancel"),
      );

      await waitFor(() =>
        expect(
          screen.queryByTestId("media-manager-remove-confirm"),
        ).not.toBeInTheDocument(),
      );
      expect(del).not.toHaveBeenCalled();
      expect(screen.getByText("Radarr")).toBeInTheDocument();
      expect(screen.getAllByTestId("media-manager-card")).toHaveLength(3);
    });

    it("leaves the connection alone when Escape closes the dialog", async () => {
      vi.spyOn(api, "fetchMediaManagerConnections").mockResolvedValue(
        threeConnections(),
      );
      const del = vi
        .spyOn(api, "deleteMediaManagerConnection")
        .mockResolvedValue(undefined);

      render(<SettingsMediaManagersTab />, { wrapper });
      fireEvent.click(
        (await screen.findAllByTestId("media-manager-remove"))[1],
      );
      fireEvent.keyDown(document, { key: "Escape" });

      await waitFor(() =>
        expect(
          screen.queryByTestId("media-manager-remove-confirm"),
        ).not.toBeInTheDocument(),
      );
      expect(del).not.toHaveBeenCalled();
      expect(screen.getAllByTestId("media-manager-card")).toHaveLength(3);
    });

    it("opens with focus on the safe choice, so Enter keeps the connection", async () => {
      vi.spyOn(api, "fetchMediaManagerConnections").mockResolvedValue(
        threeConnections(),
      );
      render(<SettingsMediaManagersTab />, { wrapper });
      fireEvent.click(
        (await screen.findAllByTestId("media-manager-remove"))[1],
      );

      expect(
        screen.getByTestId("media-manager-remove-confirm-cancel"),
      ).toHaveFocus();
      expect(
        screen.getByTestId("media-manager-remove-confirm-confirm"),
      ).not.toHaveFocus();
    });

    it("deletes only the confirmed connection, once confirmed", async () => {
      vi.spyOn(api, "fetchMediaManagerConnections").mockResolvedValue(
        threeConnections(),
      );
      const del = vi
        .spyOn(api, "deleteMediaManagerConnection")
        .mockResolvedValue(undefined);

      render(<SettingsMediaManagersTab />, { wrapper });
      fireEvent.click(
        (await screen.findAllByTestId("media-manager-remove"))[1],
      );
      fireEvent.click(
        screen.getByTestId("media-manager-remove-confirm-confirm"),
      );

      await waitFor(() => expect(del).toHaveBeenCalledTimes(1));
      expect(del).toHaveBeenCalledWith(2);
    });

    it("keeps the dialog open and says why when the removal fails", async () => {
      vi.spyOn(api, "fetchMediaManagerConnections").mockResolvedValue(
        threeConnections(),
      );
      vi.spyOn(api, "deleteMediaManagerConnection").mockRejectedValue(
        new Error("Could not reach the server."),
      );

      render(<SettingsMediaManagersTab />, { wrapper });
      fireEvent.click(
        (await screen.findAllByTestId("media-manager-remove"))[1],
      );
      fireEvent.click(
        screen.getByTestId("media-manager-remove-confirm-confirm"),
      );

      expect(await screen.findByRole("alert")).toHaveTextContent(
        "Could not reach the server.",
      );
      expect(
        screen.getByTestId("media-manager-remove-confirm"),
      ).toBeInTheDocument();
      expect(screen.getAllByTestId("media-manager-card")).toHaveLength(3);
    });
  });
});
