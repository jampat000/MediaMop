import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { RefinerJobsInspectionSection } from "./refiner/refiner-jobs-inspection-section";

vi.mock("../lib/refiner/jobs-inspection/queries", () => ({
  useRefinerJobsInspectionQuery: vi.fn(() => ({
    isPending: false,
    isError: false,
    data: {
      jobs: [
        {
          id: 1,
          status: "completed",
          job_kind: "refiner.process.test.v1",
          updated_at: "2026-04-20T00:00:00Z",
          lease_owner: null,
          lease_expires_at: null,
          dedupe_key: "dedupe-key-1",
        },
      ],
    },
  })),
  useRefinerJobCancelPendingMutation: vi.fn(() => ({
    isPending: false,
    isError: false,
    mutate: vi.fn(),
  })),
  useRefinerJobRecoverFinalizeFailedMutation: vi.fn(() => ({
    isPending: false,
    isError: false,
    mutate: vi.fn(),
  })),
}));

vi.mock("../lib/auth/queries", async (importOriginal) => {
  const original = (await importOriginal()) as Record<string, unknown>;
  return {
    ...original,
    useMeQuery: vi.fn(() => ({
      isPending: false,
      data: { id: 1, username: "admin", role: "admin" },
    })),
  };
});

function withProviders(ui: ReactNode) {
  const client = new QueryClient();
  return (
    <QueryClientProvider client={client}>
      <MemoryRouter>{ui}</MemoryRouter>
    </QueryClientProvider>
  );
}

function setViewport(width: number) {
  Object.defineProperty(window, "innerWidth", {
    configurable: true,
    writable: true,
    value: width,
  });
  window.dispatchEvent(new Event("resize"));
}

const VIEWPORTS = [320, 375, 768, 1024, 1440];

describe("responsive smoke", () => {
  afterEach(() => {
    vi.clearAllMocks();
  });

  it.each(VIEWPORTS)("renders Refiner jobs at %ipx", (width) => {
    setViewport(width);
    render(withProviders(<RefinerJobsInspectionSection />));
    expect(
      screen.getByTestId("refiner-jobs-inspection-section"),
    ).toBeInTheDocument();
    expect(screen.getByText("Jobs")).toBeInTheDocument();
  });
});
