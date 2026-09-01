import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { RefinerJobsInspectionSection } from "./refiner-jobs-inspection-section";

const useMeQuery = vi.fn();
const useSuitePauseQuery = vi.fn();
const useRefinerJobsInspectionQuery = vi.fn();
const useCancelMutation = vi.fn();
const useRecoverMutation = vi.fn();

vi.mock("../../lib/auth/queries", () => ({
  useMeQuery: () => useMeQuery(),
}));

vi.mock("../../lib/suite/pause-queries", () => ({
  useSuitePauseQuery: () => useSuitePauseQuery(),
}));

vi.mock("../../lib/refiner/jobs-inspection/queries", () => ({
  useRefinerJobsInspectionQuery: (...args: unknown[]) =>
    useRefinerJobsInspectionQuery(...args),
  useRefinerJobCancelPendingMutation: () => useCancelMutation(),
  useRefinerJobRecoverFinalizeFailedMutation: () => useRecoverMutation(),
}));

vi.mock("../../lib/ui/mm-format-date", () => ({
  useAppDateFormatter: () => (iso: string) => iso,
}));

describe("RefinerJobsInspectionSection", () => {
  beforeEach(() => {
    useMeQuery.mockReturnValue({
      isPending: false,
      data: { role: "admin" },
    });
    useSuitePauseQuery.mockReturnValue({ data: { paused: true } });
    useRefinerJobsInspectionQuery.mockReturnValue({
      isPending: false,
      isError: false,
      data: {
        jobs: [
          {
            id: 460,
            dedupe_key: "stale-sweep",
            job_kind: "refiner.work_temp_stale_sweep.v1",
            status: "pending",
            attempt_count: 0,
            max_attempts: 3,
            lease_owner: null,
            lease_expires_at: null,
            last_error: null,
            operator_message: "This job is waiting for worker capacity.",
            next_action: "No action is required.",
            technical_detail: null,
            payload_json: null,
            created_at: "2026-09-01T03:44:00Z",
            updated_at: "2026-09-01T03:44:00Z",
          },
        ],
      },
    });
    useCancelMutation.mockReturnValue({
      mutate: vi.fn(),
      isPending: false,
      isError: false,
    });
    useRecoverMutation.mockReturnValue({
      mutate: vi.fn(),
      isPending: false,
      isError: false,
    });
  });

  it("describes queued maintenance as held when the suite is paused", () => {
    render(
      <MemoryRouter>
        <RefinerJobsInspectionSection />
      </MemoryRouter>,
    );

    expect(screen.getByText("Clean temporary work files")).toBeInTheDocument();
    expect(
      screen.getByText(
        "This job is safely waiting because MediaMop is paused.",
      ),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/Use Resume at the top of the page/),
    ).toBeInTheDocument();
    expect(screen.queryByText(/worker capacity/)).not.toBeInTheDocument();
  });
});
