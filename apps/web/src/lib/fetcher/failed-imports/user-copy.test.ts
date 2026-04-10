import { describe, expect, it } from "vitest";
import {
  FETCHER_FI_TASKS_SECTION_TITLE,
  FETCHER_FI_MANUAL_SECTION_BODY,
  FETCHER_FI_MANUAL_SECTION_TITLE,
  FETCHER_FI_PAGE_FRAMING_PRIMARY,
  FETCHER_FI_PAGE_FRAMING_SCOPE,
  FETCHER_FI_SCHEDULE_MOVIES_HEADING,
  FETCHER_FI_SCHEDULE_TV_HEADING,
} from "./user-copy";

describe("fetcher failed-import user-copy (product framing)", () => {
  it("names Fetcher as owner and cites Radarr/Sonarr in the primary line", () => {
    const t = FETCHER_FI_PAGE_FRAMING_PRIMARY.toLowerCase();
    expect(t).toContain("fetcher");
    expect(t).toContain("radarr");
    expect(t).toContain("sonarr");
  });

  it("separates queue workflow from Refiner stale-file cleanup", () => {
    const s = FETCHER_FI_PAGE_FRAMING_SCOPE.toLowerCase();
    expect(s).toContain("download queue");
    expect(s).toContain("refiner");
    expect(s).toMatch(/stale|disk/);
    expect(s).toContain("not");
  });

  it("names manual queue action as a failed-import pass, not generic cleanup-drive wording", () => {
    const title = FETCHER_FI_MANUAL_SECTION_TITLE.toLowerCase();
    const body = FETCHER_FI_MANUAL_SECTION_BODY.toLowerCase();
    expect(title).not.toContain("cleanup drive");
    expect(body).not.toContain("cleanup drive");
    expect(title).toContain("failed-import");
    expect(body).toContain("download queue");
  });

  it("keeps Radarr/Sonarr on integration-specific schedule headings only", () => {
    expect(FETCHER_FI_SCHEDULE_MOVIES_HEADING).toContain("Radarr");
    expect(FETCHER_FI_SCHEDULE_TV_HEADING).toContain("Sonarr");
    expect(FETCHER_FI_SCHEDULE_MOVIES_HEADING.toLowerCase()).toContain("download-queue");
    expect(FETCHER_FI_SCHEDULE_TV_HEADING.toLowerCase()).toContain("failed-import");
  });

  it("uses task-based section title without job jargon or *arr names", () => {
    const t = FETCHER_FI_TASKS_SECTION_TITLE.toLowerCase();
    expect(t).toContain("task");
    expect(t).not.toContain("job");
    expect(t).not.toContain("radarr");
    expect(t).not.toContain("sonarr");
  });
});
