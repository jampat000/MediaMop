import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";
import { TrimmerPage } from "./trimmer-page";

describe("TrimmerPage", () => {
  it("names the trimmer durable lane and shipped job kinds honestly", () => {
    const { container } = render(
      <MemoryRouter>
        <TrimmerPage />
      </MemoryRouter>,
    );
    const page = container.querySelector(".mm-page");
    expect(page).toBeTruthy();
    const t = page!.textContent ?? "";
    expect(t).toMatch(/trimmer_jobs/);
    expect(t).toMatch(/trimmer\.trim_plan\.constraints_check\.v1/);
    expect(t).toMatch(/trimmer\.supplied_trim_plan\.json_file_write\.v1/);
    expect(t).toMatch(/MEDIAMOP_TRIMMER_WORKER_COUNT/);
    expect(t).toMatch(/plan_exports/);
    expect(screen.getByTestId("trimmer-family-trim-plan-constraints").textContent).toMatch(/transcod/i);
    expect(screen.getByTestId("trimmer-family-json-file-write").textContent).toMatch(/FFmpeg/i);
  });
});
