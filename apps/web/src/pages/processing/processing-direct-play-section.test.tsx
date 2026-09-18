import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, expect, it, vi } from "vitest";

import * as authQueries from "../../lib/auth/queries";
import * as api from "../../lib/processing/direct-play-api";
import type { DirectPlayDevices } from "../../lib/processing/direct-play-api";
import { ProcessingDirectPlaySection } from "./processing-direct-play-section";

const devices: DirectPlayDevices = {
  customised: false,
  devices: [
    {
      id: "apple_tv_4k",
      name: "Apple TV 4K",
      source: "https://www.apple.com/apple-tv-4k/specs/ (checked 2026-09-17)",
      note: "Apple's built-in player.",
      selected: true,
    },
    {
      id: "iphone",
      name: "iPhone",
      source: "https://support.apple.com/specs/iphone (checked 2026-09-10)",
      note: "The built-in video player.",
      selected: false,
    },
  ],
};

function wrapper({ children }: { children: ReactNode }) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

function asRole(role: string) {
  vi.spyOn(authQueries, "useMeQuery").mockReturnValue({
    data: { role },
  } as ReturnType<typeof authQueries.useMeQuery>);
}

afterEach(() => {
  vi.restoreAllMocks();
});

it("lists each device with its note and source, and saves the chosen ids", async () => {
  asRole("operator");
  vi.spyOn(api, "fetchDirectPlayDevices").mockResolvedValue(devices);
  const save = vi.spyOn(api, "putDirectPlayDevices").mockResolvedValue({
    ...devices,
    devices: devices.devices.map((d) => ({ ...d, selected: true })),
  });

  render(<ProcessingDirectPlaySection />, { wrapper });

  expect(
    await screen.findByText(
      "Shows which of your devices can play each file without your media server converting it. Information only — Weir never changes a file because of this.",
    ),
  ).toBeInTheDocument();
  expect(screen.getByText("Apple's built-in player.")).toBeInTheDocument();
  const source = screen.getByRole("link", { name: "Source for Apple TV 4K" });
  expect(source).toHaveAttribute(
    "href",
    "https://www.apple.com/apple-tv-4k/specs/",
  );
  expect(screen.getByText(/checked 2026-09-17/)).toBeInTheDocument();
  expect(
    screen.queryByTestId("processing-direct-play-customised"),
  ).not.toBeInTheDocument();

  expect(screen.getByRole("checkbox", { name: "Apple TV 4K" })).toBeChecked();
  const iphone = screen.getByRole("checkbox", { name: "iPhone" });
  expect(iphone).not.toBeChecked();
  fireEvent.click(iphone);
  fireEvent.click(screen.getByRole("button", { name: "Save devices" }));

  await waitFor(() => {
    expect(save).toHaveBeenCalledWith(["apple_tv_4k", "iphone"]);
  });
});

it("says when the list comes from the operator's own file", async () => {
  asRole("admin");
  vi.spyOn(api, "fetchDirectPlayDevices").mockResolvedValue({
    ...devices,
    customised: true,
  });

  render(<ProcessingDirectPlaySection />, { wrapper });

  expect(
    await screen.findByTestId("processing-direct-play-customised"),
  ).toHaveTextContent(/your own direct-play-devices\.json/);
});

it("shows a viewer the list read-only", async () => {
  asRole("viewer");
  vi.spyOn(api, "fetchDirectPlayDevices").mockResolvedValue(devices);
  const save = vi.spyOn(api, "putDirectPlayDevices");

  render(<ProcessingDirectPlaySection />, { wrapper });

  const iphone = await screen.findByRole("checkbox", { name: "iPhone" });
  expect(iphone).toBeDisabled();
  fireEvent.click(iphone);
  const button = screen.getByRole("button", { name: "Save devices" });
  expect(button).toBeDisabled();
  fireEvent.click(button);
  expect(save).not.toHaveBeenCalled();
  expect(
    screen.getByText(/Only an operator or admin can change/),
  ).toBeInTheDocument();
});
