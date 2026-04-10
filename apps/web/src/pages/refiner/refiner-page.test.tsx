import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";
import { RefinerPage } from "./refiner-page";

describe("RefinerPage (product boundary)", () => {
  it("does not present download-queue failed-import inspection as a Refiner feature", () => {
    render(
      <MemoryRouter>
        <RefinerPage />
      </MemoryRouter>,
    );
    expect(screen.queryByTestId("fetcher-failed-imports-workspace")).toBeNull();
    expect(screen.queryByTestId("fetcher-failed-imports-settings")).toBeNull();
    expect(screen.queryByTestId("fetcher-failed-imports-status-filter")).toBeNull();
  });

  it("points operators at Fetcher for Radarr/Sonarr queue failed-import workflow", () => {
    render(
      <MemoryRouter>
        <RefinerPage />
      </MemoryRouter>,
    );
    const link = screen.getByRole("link", { name: "Fetcher" });
    expect(link).toHaveAttribute("href", "/app/fetcher");
    const main = screen.getByTestId("refiner-scope-page");
    expect(main.textContent).toMatch(/Radarr/i);
    expect(main.textContent).toMatch(/Sonarr/i);
    expect(main.textContent).toMatch(/download-queue/i);
  });
});
