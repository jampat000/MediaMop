import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { MemoryRouter } from "react-router-dom";
import { PrunerPage } from "./pruner-page";

describe("PrunerPage", () => {
  it("describes removal focus and Phase 1 honest empty surface", () => {
    render(
      <MemoryRouter>
        <PrunerPage />
      </MemoryRouter>,
    );
    const t = screen.getByTestId("pruner-scope-page").textContent ?? "";
    expect(t).toMatch(/Pruner/);
    expect(t).toMatch(/MEDIAMOP_PRUNER_WORKER_COUNT/);
    expect(t).toMatch(/No removal jobs/);
    expect(t).toMatch(/pruner_jobs/);
  });
});
