import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";
import { RefinerPage } from "./refiner-page";

describe("RefinerPage (hero compression)", () => {
  it("does not host Fetcher failed-import UI", () => {
    render(
      <MemoryRouter>
        <RefinerPage />
      </MemoryRouter>,
    );
    expect(screen.queryByTestId("fetcher-failed-imports-workspace")).toBeNull();
    expect(screen.queryByTestId("fetcher-failed-imports-settings")).toBeNull();
    expect(screen.queryByTestId("fetcher-failed-imports-status-filter")).toBeNull();
  });

  it("hero and shipped-family copy stay Refiner-scoped (no Fetcher lane language)", () => {
    const { container } = render(
      <MemoryRouter>
        <RefinerPage />
      </MemoryRouter>,
    );
    const page = container.querySelector(".mm-page");
    expect(page).toBeTruthy();
    const t = page!.textContent ?? "";
    expect(t).toMatch(/Refin/i);
    // Strip SQL table name so we do not false-positive on the substring "fetcher" inside ``fetcher_jobs``.
    expect(t.replace(/fetcher_jobs/gi, "")).not.toMatch(/Fetcher/i);
    expect(t).toMatch(/refiner_jobs/);
    expect(t).toMatch(/fetcher_jobs/);
    expect(t).toMatch(/refiner\.supplied_payload_evaluation\.v1/);
    expect(t).toMatch(/refiner\.candidate_gate\.v1/);
    expect(t).toMatch(/refiner\.file\.remux_pass\.v1/);
  });

  it("documents supplied payload evaluation without overstating library or disk work", () => {
    render(
      <MemoryRouter>
        <RefinerPage />
      </MemoryRouter>,
    );
    const li = screen.getByTestId("refiner-family-supplied-payload-evaluation");
    const t = li.textContent ?? "";
    expect(t).toMatch(/does not.*call Radarr or Sonarr/i);
    expect(t).toMatch(/library-wide audit/i);
    expect(t).toMatch(/filesystem sweep/i);
    expect(t).toMatch(/rows/);
  });

  it("documents file remux pass with dry-run default and ffprobe honestly", () => {
    render(
      <MemoryRouter>
        <RefinerPage />
      </MemoryRouter>,
    );
    const li = screen.getByTestId("refiner-family-file-remux-pass");
    const t = li.textContent ?? "";
    expect(t).toMatch(/dry run/i);
    expect(t).toMatch(/ffprobe/i);
    expect(t).toMatch(/MEDIAMOP_REFINER_REMUX_MEDIA_ROOT/);
  });

  it("documents candidate gate live queue behavior honestly", () => {
    render(
      <MemoryRouter>
        <RefinerPage />
      </MemoryRouter>,
    );
    const li = screen.getByTestId("refiner-family-candidate-gate");
    const t = li.textContent ?? "";
    expect(t).toMatch(/Radarr/i);
    expect(t).toMatch(/Sonarr/i);
    expect(t).toMatch(/download queue/i);
  });

  it("has no Fetcher link on the page", () => {
    render(
      <MemoryRouter>
        <RefinerPage />
      </MemoryRouter>,
    );
    expect(screen.queryByRole("link", { name: "Fetcher" })).toBeNull();
  });
});
