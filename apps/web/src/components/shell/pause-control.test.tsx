import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, expect, it, vi } from "vitest";

import * as authQueries from "../../lib/auth/queries";
import type { SuitePause } from "../../lib/suite/pause-api";
import * as pauseQueries from "../../lib/suite/pause-queries";
import { PauseControl } from "./pause-control";

const mutate = vi.fn();

function wrapper({ children }: { children: ReactNode }) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

function state(over: Partial<SuitePause> = {}): SuitePause {
  return {
    paused: false,
    paused_until: null,
    scan_while_paused: true,
    reason: "",
    in_flight_policy:
      "Work already running finishes. Pausing stops MediaMop starting anything new.",
    ...over,
  };
}

function setup(pause: SuitePause, role = "operator") {
  vi.spyOn(authQueries, "useMeQuery").mockReturnValue({
    data: { role },
  } as ReturnType<typeof authQueries.useMeQuery>);
  vi.spyOn(pauseQueries, "useSuitePauseQuery").mockReturnValue({
    data: pause,
  } as ReturnType<typeof pauseQueries.useSuitePauseQuery>);
  vi.spyOn(pauseQueries, "useSaveSuitePause").mockReturnValue({
    mutate,
    isPending: false,
  } as unknown as ReturnType<typeof pauseQueries.useSaveSuitePause>);
}

afterEach(() => {
  vi.restoreAllMocks();
  mutate.mockReset();
});

it("offers a pause with an expiry, so it cannot be forgotten", () => {
  setup(state());

  render(<PauseControl />, { wrapper });
  fireEvent.click(screen.getByTestId("pause-open"));
  fireEvent.click(screen.getByTestId("pause-for-120"));

  expect(mutate).toHaveBeenCalledWith({
    paused: true,
    pause_for_minutes: 120,
    scan_while_paused: true,
  });
});

it("still allows a pause with no expiry", () => {
  setup(state());

  render(<PauseControl />, { wrapper });
  fireEvent.click(screen.getByTestId("pause-open"));
  fireEvent.click(screen.getByTestId("pause-for-indefinite"));

  expect(mutate).toHaveBeenCalledWith({
    paused: true,
    pause_for_minutes: null,
    scan_while_paused: true,
  });
});

it("says what happens to work already running rather than leaving it to be assumed", () => {
  setup(state());

  render(<PauseControl />, { wrapper });
  fireEvent.click(screen.getByTestId("pause-open"));

  expect(screen.getByTestId("pause-policy")).toHaveTextContent(
    /already running finishes/i,
  );
});

it("shows the reason, which carries when the pause lifts", () => {
  setup(
    state({
      paused: true,
      paused_until: "2026-08-26T16:00:00Z",
      reason:
        "Processing is paused. MediaMop will start work again automatically at 2026-08-26 16:00 UTC.",
    }),
  );

  render(<PauseControl />, { wrapper });

  expect(screen.getByTestId("pause-badge")).toHaveTextContent("Paused");
  expect(screen.getByTestId("pause-reason")).toHaveTextContent(
    "2026-08-26 16:00 UTC",
  );
});

it("resumes without inventing a duration", () => {
  setup(state({ paused: true, reason: "Processing is paused." }));

  render(<PauseControl />, { wrapper });
  fireEvent.click(screen.getByTestId("pause-resume"));

  expect(mutate).toHaveBeenCalledWith({
    paused: false,
    scan_while_paused: true,
  });
});

it("lets a viewer see a pause but not change it", () => {
  setup(state({ paused: true, reason: "Processing is paused." }), "viewer");

  render(<PauseControl />, { wrapper });

  expect(screen.getByTestId("pause-badge")).toBeInTheDocument();
  expect(screen.queryByTestId("pause-resume")).not.toBeInTheDocument();
});

it("shows a viewer nothing at all when processing is running normally", () => {
  setup(state(), "viewer");

  const { container } = render(<PauseControl />, { wrapper });

  expect(container).toBeEmptyDOMElement();
});
