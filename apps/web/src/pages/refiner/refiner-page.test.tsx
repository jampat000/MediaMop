import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";
import type { UserPublic } from "../../lib/api/types";
import { qk } from "../../lib/auth/queries";
import { refinerPathSettingsQueryKey, refinerRuntimeSettingsQueryKey } from "../../lib/refiner/queries";
import type { RefinerPathSettingsOut, RefinerRuntimeSettingsOut } from "../../lib/refiner/types";
import { RefinerPage } from "./refiner-page";

const operatorMe: UserPublic = { id: 1, username: "alice", role: "operator" };

const minimalRefinerPathSettings: RefinerPathSettingsOut = {
  refiner_watched_folder: null,
  refiner_work_folder: null,
  refiner_output_folder: "",
  resolved_default_work_folder: "/tmp/mm-default-refiner-work",
  effective_work_folder: "/tmp/mm-default-refiner-work",
  updated_at: "2026-04-11T00:00:00Z",
};

const minimalRefinerRuntimeSettings: RefinerRuntimeSettingsOut = {
  in_process_refiner_worker_count: 0,
  in_process_workers_disabled: true,
  in_process_workers_enabled: false,
  worker_mode_summary: "In-process Refiner workers are off (0).",
  sqlite_throughput_note: "SQLite note for tests.",
  configuration_note: "Change MEDIAMOP_REFINER_WORKER_COUNT in apps/backend/.env, then restart.",
  visibility_note: "Snapshot note for tests.",
};

function wrap(ui: ReactNode, client: QueryClient) {
  return (
    <QueryClientProvider client={client}>
      <MemoryRouter>{ui}</MemoryRouter>
    </QueryClientProvider>
  );
}

function renderRefinerPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  qc.setQueryData(refinerRuntimeSettingsQueryKey, minimalRefinerRuntimeSettings);
  qc.setQueryData(refinerPathSettingsQueryKey, minimalRefinerPathSettings);
  qc.setQueryData(qk.me, operatorMe);
  return render(wrap(<RefinerPage />, qc));
}

describe("RefinerPage (hero compression)", () => {
  it("does not host Fetcher failed-import UI", () => {
    renderRefinerPage();
    expect(screen.queryByTestId("fetcher-failed-imports-workspace")).toBeNull();
    expect(screen.queryByTestId("fetcher-failed-imports-settings")).toBeNull();
    expect(screen.queryByTestId("fetcher-failed-imports-status-filter")).toBeNull();
  });

  it("hero and shipped-family copy stay Refiner-scoped (no Fetcher lane language)", () => {
    const { container } = renderRefinerPage();
    const page = container.querySelector(".mm-page");
    expect(page).toBeTruthy();
    const t = page!.textContent ?? "";
    expect(t).toMatch(/Refin/i);
    // Strip SQL table name so we do not false-positive on the substring "fetcher" inside ``fetcher_jobs``.
    expect(t.replace(/fetcher_jobs/gi, "")).not.toMatch(/Fetcher/i);
    expect(t).toMatch(/refiner_jobs/);
    expect(t).toMatch(/fetcher_jobs/);
    expect(t).toMatch(/refiner\.supplied_payload_evaluation\.v1/);
    expect(t).toMatch(/refiner\.candidate_gate\.v1/);
    expect(t).toMatch(/refiner\.file\.remux_pass\.v1/);
  });

  it("documents supplied payload evaluation without overstating library or disk work", () => {
    renderRefinerPage();
    const li = screen.getByTestId("refiner-family-supplied-payload-evaluation");
    const text = li.textContent ?? "";
    expect(text).toMatch(/does not.*call Radarr or Sonarr/i);
    expect(text).toMatch(/library-wide audit/i);
    expect(text).toMatch(/filesystem sweep/i);
    expect(text).toMatch(/rows/);
  });

  it("documents file remux pass with dry-run default and ffprobe honestly", () => {
    renderRefinerPage();
    const li = screen.getByTestId("refiner-family-file-remux-pass");
    const text = li.textContent ?? "";
    expect(text).toMatch(/dry run/i);
    expect(text).toMatch(/ffprobe/i);
    expect(text).toMatch(/saved.*watched folder/i);
    expect(text).toMatch(/enqueue is rejected/i);
    expect(text).toMatch(/Activity feed/i);
  });

  it("documents candidate gate live queue behavior honestly", () => {
    renderRefinerPage();
    const li = screen.getByTestId("refiner-family-candidate-gate");
    const text = li.textContent ?? "";
    expect(text).toMatch(/Radarr/i);
    expect(text).toMatch(/Sonarr/i);
    expect(text).toMatch(/download queue/i);
  });

  it("has no Fetcher link on the page", () => {
    renderRefinerPage();
    expect(screen.queryByRole("link", { name: "Fetcher" })).toBeNull();
  });

  it("surfaces Refiner-only in-process worker concurrency with env restart honesty", () => {
    renderRefinerPage();
    const block = screen.getByTestId("refiner-runtime-settings");
    expect(block).toBeInTheDocument();
    expect(block.textContent).toMatch(/MEDIAMOP_REFINER_WORKER_COUNT/i);
    expect(block.textContent).toMatch(/0/);
    expect(block.textContent?.toLowerCase()).toMatch(/sqlite/);
  });
});
