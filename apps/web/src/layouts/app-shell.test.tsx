import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { AppShell } from "./app-shell";

const logoutMutate = vi.fn();
const scrollToMock = vi.fn();

vi.mock("../lib/auth/queries", () => ({
  useLogoutMutation: () => ({
    mutate: logoutMutate,
    isPending: false,
  }),
  // The shell now carries the pause control, which needs to know whether the signed-in
  // person may change it.
  useMeQuery: () => ({ data: { role: "operator" } }),
}));

vi.mock("../lib/pause/pause-queries", () => ({
  usePauseQuery: () => ({
    data: {
      paused: false,
      paused_until: null,
      scan_while_paused: true,
      reason: "",
      in_flight_policy: "Work already running finishes.",
    },
  }),
  useSavePause: () => ({ mutate: vi.fn(), isPending: false }),
}));

vi.mock("../lib/system/readiness-queries", () => ({
  useSystemReadinessQuery: () => ({
    data: {
      version: "2.1.2",
    },
  }),
}));

vi.mock("../lib/suite/queries", () => ({
  useSuiteSettingsQuery: () => ({
    data: {
      product_display_name: "MediaMop",
    },
  }),
}));

describe("AppShell", () => {
  beforeEach(() => {
    logoutMutate.mockReset();
    scrollToMock.mockReset();
    window.scrollTo = scrollToMock;
  });

  it("keeps only the version and sign-out controls in the sidebar footer", () => {
    render(
      <MemoryRouter initialEntries={["/"]}>
        <Routes>
          <Route path="/" element={<AppShell />}>
            <Route index element={<div>In hand</div>} />
          </Route>
        </Routes>
      </MemoryRouter>,
    );

    expect(screen.getByText("Version 2.1.2")).toBeInTheDocument();
    expect(screen.getByTestId("sign-out")).toBeInTheDocument();
    expect(screen.queryByTestId("sidebar-support")).not.toBeInTheDocument();
    expect(screen.queryByText("Support MediaMop")).not.toBeInTheDocument();
    expect(screen.queryByText(/supporter licence/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/licence checks/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/feature limits/i)).not.toBeInTheDocument();
  });

  it("has no Dashboard entry; In hand is the main screen (#459)", () => {
    render(
      <MemoryRouter initialEntries={["/"]}>
        <Routes>
          <Route path="/" element={<AppShell />}>
            <Route index element={<div>Main</div>} />
          </Route>
        </Routes>
      </MemoryRouter>,
    );

    expect(screen.getByRole("link", { name: "In hand" })).toBeInTheDocument();
    expect(
      screen.queryByRole("link", { name: "Dashboard" }),
    ).not.toBeInTheDocument();
  });

  it("returns document scrolling to the top when the route changes", () => {
    render(
      <MemoryRouter initialEntries={["/"]}>
        <Routes>
          <Route path="/" element={<AppShell />}>
            <Route index element={<div>In hand page</div>} />
            <Route path="activity" element={<div>Activity page</div>} />
          </Route>
        </Routes>
      </MemoryRouter>,
    );

    fireEvent.click(screen.getByRole("link", { name: "Activity" }));

    expect(screen.getByText("Activity page")).toBeInTheDocument();
    expect(scrollToMock).toHaveBeenLastCalledWith(0, 0);
  });
});
