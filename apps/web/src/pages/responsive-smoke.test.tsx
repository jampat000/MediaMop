import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ProcessingJobsInspectionSection } from "./processing/processing-jobs-inspection-section";

vi.mock("../lib/processing/jobs-inspection/queries", () => ({
  useProcessingJobsInspectionQuery: vi.fn(() => ({
    isPending: false,
    isError: false,
    data: {
      jobs: [
        {
          id: 1,
          status: "completed",
          job_kind: "processing.process.test.v1",
          updated_at: "2026-04-20T00:00:00Z",
          lease_owner: null,
          lease_expires_at: null,
          dedupe_key: "dedupe-key-1",
        },
      ],
    },
  })),
  useProcessingJobCancelPendingMutation: vi.fn(() => ({
    isPending: false,
    isError: false,
    mutate: vi.fn(),
  })),
  useProcessingJobRecoverFinalizeFailedMutation: vi.fn(() => ({
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

  it.each(VIEWPORTS)("renders Processing jobs at %ipx", (width) => {
    setViewport(width);
    render(withProviders(<ProcessingJobsInspectionSection />));
    expect(
      screen.getByTestId("processing-jobs-inspection-section"),
    ).toBeInTheDocument();
    expect(screen.getByText("Jobs")).toBeInTheDocument();
  });
});
