import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, expect, it, vi } from "vitest";

import * as authQueries from "../../lib/auth/queries";
import type { MaintenanceState } from "../../lib/processing/maintenance-api";
import * as maintenanceQueries from "../../lib/processing/maintenance-queries";
import { ProcessingMaintenanceSection } from "./processing-maintenance-section";

const mutate = vi.fn();

function wrapper({ children }: { children: ReactNode }) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

function state(over: Partial<MaintenanceState> = {}): MaintenanceState {
  return {
    families: [
      {
        family: "work_temp_stale_sweep",
        enabled: true,
        description: "Reclaims Weir's own stale working files.",
        pending: 0,
        running: 0,
        last_completed_at: null,
        last_failed_at: null,
        last_error: null,
      },
      {
        family: "failure_cleanup",
        enabled: false,
        description:
          "Removes the source release folder after a file has failed terminally. This deletes the original.",
        pending: 0,
        running: 0,
        last_completed_at: null,
        last_failed_at: null,
        last_error: null,
      },
    ],
    ...over,
  };
}

function setup(data: MaintenanceState, role = "operator") {
  vi.spyOn(authQueries, "useMeQuery").mockReturnValue({
    data: { role },
  } as ReturnType<typeof authQueries.useMeQuery>);
  vi.spyOn(maintenanceQueries, "useProcessingMaintenanceQuery").mockReturnValue(
    {
      data,
    } as ReturnType<typeof maintenanceQueries.useProcessingMaintenanceQuery>,
  );
  vi.spyOn(
    maintenanceQueries,
    "useProcessingRuntimeSettingsQuery",
  ).mockReturnValue({ data: undefined } as ReturnType<
    typeof maintenanceQueries.useProcessingRuntimeSettingsQuery
  >);
  vi.spyOn(maintenanceQueries, "useRunProcessingMaintenance").mockReturnValue({
    mutateAsync: mutate,
    isPending: false,
  } as unknown as ReturnType<
    typeof maintenanceQueries.useRunProcessingMaintenance
  >);
}

afterEach(() => {
  vi.restoreAllMocks();
  mutate.mockReset();
});

it("lists every promoted family and whether it is scheduled", async () => {
  setup(state());

  render(<ProcessingMaintenanceSection />, { wrapper });

  expect(
    await screen.findByTestId("processing-maintenance-work_temp_stale_sweep"),
  ).toHaveTextContent("scheduled");
  expect(
    screen.getByTestId("processing-maintenance-failure_cleanup"),
  ).toHaveTextContent("not scheduled");
});

it("carries the warning where the switch is", async () => {
  setup(state());

  render(<ProcessingMaintenanceSection />, { wrapper });

  // Failure cleanup deletes originals, and the operator sees that beside the button.
  expect(
    await screen.findByTestId("processing-maintenance-failure_cleanup"),
  ).toHaveTextContent(/deletes the original/i);
});

it("runs a family for one scope", async () => {
  setup(state());
  mutate.mockResolvedValue({
    queued: true,
    detail: "Queued a work file sweep.",
  });

  render(<ProcessingMaintenanceSection />, { wrapper });
  fireEvent.click(
    await screen.findByTestId(
      "processing-maintenance-run-work_temp_stale_sweep-tv",
    ),
  );

  expect(mutate).toHaveBeenCalledWith({
    family: "work_temp_stale_sweep",
    mediaScope: "tv",
  });
});

it("shows the server's own words when nothing was queued", async () => {
  setup(state());
  mutate.mockResolvedValue({
    queued: false,
    detail: "A failure cleanup for this scope is already waiting or running.",
  });

  render(<ProcessingMaintenanceSection />, { wrapper });
  fireEvent.click(
    await screen.findByTestId(
      "processing-maintenance-run-failure_cleanup-movie",
    ),
  );

  expect(
    await screen.findByTestId("processing-maintenance-notice"),
  ).toHaveTextContent(/already waiting or running/);
});

it("reports a running family rather than showing it as idle", async () => {
  setup(
    state({
      families: [
        {
          family: "work_temp_stale_sweep",
          enabled: true,
          description: "Reclaims stale working files.",
          pending: 0,
          running: 1,
          last_completed_at: null,
          last_failed_at: null,
          last_error: null,
        },
      ],
    }),
  );

  render(<ProcessingMaintenanceSection />, { wrapper });

  expect(
    await screen.findByTestId("processing-maintenance-work_temp_stale_sweep"),
  ).toHaveTextContent(/Running now/);
});

it("surfaces the reason a run failed", async () => {
  setup(
    state({
      families: [
        {
          family: "failure_cleanup",
          enabled: true,
          description: "Removes the source release folder.",
          pending: 0,
          running: 0,
          last_completed_at: null,
          last_failed_at: "2026-08-26T14:00:00Z",
          last_error: "The work folder was missing.",
        },
      ],
    }),
  );

  render(<ProcessingMaintenanceSection />, { wrapper });

  expect(
    await screen.findByTestId("processing-maintenance-failure_cleanup"),
  ).toHaveTextContent("The work folder was missing.");
});

it("does not offer a viewer the run buttons", async () => {
  setup(state(), "viewer");

  render(<ProcessingMaintenanceSection />, { wrapper });

  await screen.findByTestId("processing-maintenance-work_temp_stale_sweep");
  expect(
    screen.queryByTestId(
      "processing-maintenance-run-work_temp_stale_sweep-movie",
    ),
  ).not.toBeInTheDocument();
});
