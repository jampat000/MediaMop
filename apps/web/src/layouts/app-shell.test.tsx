import { fireEvent, render, screen, within } from "@testing-library/react";
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
      product_display_name: "Weir",
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
            <Route index element={<div>Home</div>} />
          </Route>
        </Routes>
      </MemoryRouter>,
    );

    expect(screen.getByText("Version 2.1.2")).toBeInTheDocument();
    expect(screen.getByTestId("sign-out")).toBeInTheDocument();
    expect(screen.queryByTestId("sidebar-support")).not.toBeInTheDocument();
    expect(screen.queryByText("Support Weir")).not.toBeInTheDocument();
    expect(screen.queryByText(/supporter licence/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/licence checks/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/feature limits/i)).not.toBeInTheDocument();
  });

  it("has no Dashboard entry; Home is the main screen (#459)", () => {
    render(
      <MemoryRouter initialEntries={["/"]}>
        <Routes>
          <Route path="/" element={<AppShell />}>
            <Route index element={<div>Main</div>} />
          </Route>
        </Routes>
      </MemoryRouter>,
    );

    expect(screen.getByRole("link", { name: "Home" })).toBeInTheDocument();
    expect(
      screen.queryByRole("link", { name: "Dashboard" }),
    ).not.toBeInTheDocument();
  });

  it("sends every nav item to the screen its label names, and has no others", () => {
    render(
      <MemoryRouter initialEntries={["/"]}>
        <Routes>
          <Route path="/" element={<AppShell />}>
            <Route index element={<div>Main</div>} />
          </Route>
        </Routes>
      </MemoryRouter>,
    );

    const nav = screen.getByRole("navigation", { name: "Primary" });
    const items = within(nav)
      .getAllByRole("link")
      .map((link) => [link.textContent, link.getAttribute("href")]);

    // The whole nav, in order. A new entry has to be added here deliberately, and a label that
    // stops matching its destination fails rather than quietly misleading someone.
    expect(items).toEqual([
      ["Home", "/"],
      ["Activity", "/activity"],
      ["Processing", "/processing"],
      ["Settings", "/settings"],
    ]);
  });

  it("marks only the current screen, and marks nothing on a page that is not one", () => {
    const { unmount } = render(
      <MemoryRouter initialEntries={["/activity"]}>
        <Routes>
          <Route path="/" element={<AppShell />}>
            <Route index element={<div>Home</div>} />
            <Route path="activity" element={<div>Activity</div>} />
            <Route path="*" element={<div>Not found</div>} />
          </Route>
        </Routes>
      </MemoryRouter>,
    );

    const current = () =>
      within(screen.getByRole("navigation", { name: "Primary" }))
        .getAllByRole("link")
        .filter((link) => link.getAttribute("aria-current") === "page")
        .map((link) => link.textContent);

    expect(current()).toEqual(["Activity"]);
    unmount();

    // `/dashboard` is the Not found page now that 3.0.0 dropped its redirect (#585). Home is
    // the index route, so it must not claim to be the screen you are on.
    render(
      <MemoryRouter initialEntries={["/dashboard"]}>
        <Routes>
          <Route path="/" element={<AppShell />}>
            <Route index element={<div>Home</div>} />
            <Route path="*" element={<div>Not found</div>} />
          </Route>
        </Routes>
      </MemoryRouter>,
    );

    expect(current()).toEqual([]);
  });

  it("names the sidebar landmark after the product", () => {
    render(
      <MemoryRouter initialEntries={["/"]}>
        <Routes>
          <Route path="/" element={<AppShell />}>
            <Route index element={<div>Main</div>} />
          </Route>
        </Routes>
      </MemoryRouter>,
    );

    // It was "Product", left over from the suite this stopped being.
    expect(
      screen.getByRole("complementary", { name: "Weir" }),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("complementary", { name: "Product" }),
    ).not.toBeInTheDocument();
  });

  it("returns document scrolling to the top when the route changes", () => {
    render(
      <MemoryRouter initialEntries={["/"]}>
        <Routes>
          <Route path="/" element={<AppShell />}>
            <Route index element={<div>Home page</div>} />
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
