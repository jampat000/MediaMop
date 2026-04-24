import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { SetupPage } from "./setup-page";

const navigateMock = vi.fn();
const mutateAsyncMock = vi.fn();

vi.mock("react-router-dom", async (importOriginal) => {
  const actual = await importOriginal<typeof import("react-router-dom")>();
  return {
    ...actual,
    useNavigate: () => navigateMock,
  };
});

vi.mock("../../lib/auth/queries", () => ({
  useMeQuery: () => ({ isPending: false, data: null }),
  useBootstrapStatusQuery: () => ({
    isPending: false,
    isError: false,
    data: { bootstrap_allowed: true, reason: "no_admin_user" },
  }),
  useBootstrapMutation: () => ({
    isPending: false,
    isError: false,
    error: null,
    mutateAsync: mutateAsyncMock,
  }),
}));

function wrap(ui: ReactNode) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return (
    <QueryClientProvider client={client}>
      <MemoryRouter>{ui}</MemoryRouter>
    </QueryClientProvider>
  );
}

describe("SetupPage", () => {
  beforeEach(() => {
    navigateMock.mockReset();
    mutateAsyncMock.mockReset();
  });

  it("blocks bootstrap submit when password is shorter than 8 characters", async () => {
    render(wrap(<SetupPage />));

    fireEvent.change(screen.getByTestId("setup-username"), { target: { value: "admin" } });
    fireEvent.change(screen.getByTestId("setup-password"), { target: { value: "short" } });
    fireEvent.submit(screen.getByTestId("setup-form"));

    expect(mutateAsyncMock).not.toHaveBeenCalled();
    expect(screen.getByRole("alert")).toHaveTextContent("Password must be at least 8 characters.");
  });

  it("submits bootstrap when username and password meet the requirements", async () => {
    mutateAsyncMock.mockResolvedValue({ message: "ok", username: "admin" });

    render(wrap(<SetupPage />));

    fireEvent.change(screen.getByTestId("setup-username"), { target: { value: " admin " } });
    fireEvent.change(screen.getByTestId("setup-password"), {
      target: { value: "password-strong" },
    });
    fireEvent.submit(screen.getByTestId("setup-form"));

    expect(mutateAsyncMock).toHaveBeenCalledWith({
      username: "admin",
      password: "password-strong",
    });
  });
});
