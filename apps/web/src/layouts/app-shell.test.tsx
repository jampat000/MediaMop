import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { AppShell } from "./app-shell";

const logoutMutate = vi.fn();

vi.mock("../lib/auth/queries", () => ({
  useLogoutMutation: () => ({
    mutate: logoutMutate,
    isPending: false,
  }),
}));

vi.mock("../lib/dashboard/queries", () => ({
  useDashboardStatusQuery: () => ({
    data: {
      system: {
        api_version: "2.1.1",
      },
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
  });

  it("keeps only the version and sign-out controls in the sidebar footer", () => {
    render(
      <MemoryRouter initialEntries={["/"]}>
        <Routes>
          <Route path="/" element={<AppShell />}>
            <Route index element={<div>Dashboard</div>} />
          </Route>
        </Routes>
      </MemoryRouter>,
    );

    expect(screen.getByText("Version 2.1.1")).toBeInTheDocument();
    expect(screen.getByTestId("sign-out")).toBeInTheDocument();
    expect(screen.queryByTestId("sidebar-support")).not.toBeInTheDocument();
    expect(screen.queryByText("Support MediaMop")).not.toBeInTheDocument();
    expect(screen.queryByText(/supporter licence/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/licence checks/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/feature limits/i)).not.toBeInTheDocument();
  });
});
