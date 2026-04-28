import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { StartupGate } from "./startup-gate";

describe("StartupGate", () => {
  beforeEach(() => {
    vi.useRealTimers();
  });

  afterEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  it("shows startup state until backend readiness is confirmed", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => ({
        ok: false,
        json: async () => ({
          ready: false,
          status: "starting",
          startup_seconds: 0.1,
          steps: [{ name: "database", status: "starting", detail: "Preparing database." }],
        }),
      })),
    );

    render(
      <StartupGate>
        <div>App mounted</div>
      </StartupGate>,
    );

    expect(await screen.findByText("Starting MediaMop...")).toBeInTheDocument();
    expect(screen.queryByText("App mounted")).not.toBeInTheDocument();
    expect(screen.getByText("Preparing database.")).toBeInTheDocument();
  });

  it("mounts children after backend readiness is confirmed", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => ({
        ok: true,
        json: async () => ({
          ready: true,
          status: "ready",
          startup_seconds: 0.2,
          steps: [
            { name: "database", status: "ready", detail: "Database ready." },
            { name: "workers", status: "ready", detail: "Workers ready." },
          ],
        }),
      })),
    );

    render(
      <StartupGate>
        <div>App mounted</div>
      </StartupGate>,
    );

    await waitFor(() => expect(screen.getByText("App mounted")).toBeInTheDocument());
    expect(screen.queryByText("Starting MediaMop...")).not.toBeInTheDocument();
  });
});
