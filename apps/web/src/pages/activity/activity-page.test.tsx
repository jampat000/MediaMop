import { fireEvent, render, screen, within } from "@testing-library/react";
import { beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import { ActivityPage } from "./activity-page";

const useActivityRecentQuery = vi.fn();

vi.mock("../../lib/activity/queries", () => ({
  activityRecentKey: ["activity", "recent"],
  useActivityRecentQuery: (...args: unknown[]) => useActivityRecentQuery(...args),
}));

vi.mock("../../lib/activity/use-activity-stream-invalidation", () => ({
  useActivityStreamInvalidation: vi.fn(),
}));

vi.mock("../../lib/ui/mm-format-date", () => ({
  useAppDateFormatter: () => (iso: string) => iso,
}));

beforeAll(() => {
  class EventSourceStub {
    addEventListener = vi.fn();
    removeEventListener = vi.fn();
    close = vi.fn();
  }
  vi.stubGlobal("EventSource", EventSourceStub);
});

describe("ActivityPage", () => {
  beforeEach(() => {
    useActivityRecentQuery.mockReset();
  });

  it("renders summary cards and filters", () => {
    useActivityRecentQuery.mockReturnValue({
      isPending: false,
      isError: false,
      data: {
        items: [
          {
            id: 1,
            created_at: "2026-04-24T00:00:00Z",
            event_type: "subber.library_scan_enqueued",
            module: "subber",
            title: "Subber library scan (movies)",
            detail: '{"enqueued":0,"media_scope":"movies"}',
          },
        ],
        total: 1,
        system_events: 0,
      },
    });

    render(<ActivityPage />);

    expect(screen.getByText("Showing now")).toBeInTheDocument();
    expect(screen.getByText("Matches in store")).toBeInTheDocument();
    expect(screen.getByText("System events")).toBeInTheDocument();
    expect(screen.getByText("Refresh")).toBeInTheDocument();
    expect(screen.getByDisplayValue("All modules")).toBeInTheDocument();
    expect(screen.getByDisplayValue("All events")).toBeInTheDocument();
    expect(screen.getByText("Movies library scan checked")).toBeInTheDocument();
    expect(screen.getByText("No new movies needed a subtitle scan.")).toBeInTheDocument();
    expect(screen.getByText("Nothing new found")).toBeInTheDocument();
  });

  it("shows a proper empty state when no events match", async () => {
    useActivityRecentQuery.mockReturnValue({
      isPending: false,
      isError: false,
      data: { items: [], total: 0, system_events: 0 },
    });

    render(<ActivityPage />);

    fireEvent.click(screen.getByRole("button", { name: "Apply filters" }));
    expect(screen.getByText("No activity matched the current filters.")).toBeInTheDocument();
  });

  it("includes system in the module filter", () => {
    useActivityRecentQuery.mockReturnValue({
      isPending: false,
      isError: false,
      data: { items: [], total: 0, system_events: 0 },
    });

    render(<ActivityPage />);
    const select = screen.getByDisplayValue("All modules");
    const options = within(select.closest("label")!).getAllByRole("option");
    expect(options.map((option) => option.textContent)).toContain("System");
  });
});
