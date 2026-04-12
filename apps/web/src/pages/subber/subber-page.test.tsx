import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";
import { SubberPage } from "./subber-page";

describe("SubberPage", () => {
  it("names the subber durable lane and shipped job kind honestly", () => {
    const { container } = render(
      <MemoryRouter>
        <SubberPage />
      </MemoryRouter>,
    );
    const page = container.querySelector(".mm-page");
    expect(page).toBeTruthy();
    const t = page!.textContent ?? "";
    expect(t).toMatch(/subber_jobs/);
    expect(t).toMatch(/subber\.supplied_cue_timeline\.constraints_check\.v1/);
    expect(t).toMatch(/MEDIAMOP_SUBBER_WORKER_COUNT/);
    expect(screen.getByTestId("subber-family-cue-timeline-constraints").textContent).toMatch(/OCR/i);
  });
});
