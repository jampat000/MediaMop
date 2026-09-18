import { describe, expect, it } from "vitest";
import type { ActivityEventItem } from "../api/types";
import { activityTriggerLabel, summarizeRun } from "./activity-runs";

function ev(
  overrides: Partial<ActivityEventItem> & { id: number },
): ActivityEventItem {
  return {
    created_at: "2026-09-16T22:00:00Z",
    event_type: "processing.file_remux_pass_completed",
    module: "processing",
    title: "t",
    ...overrides,
  };
}

describe("activity runs", () => {
  it("names triggers in plain words and never guesses a missing one", () => {
    expect(activityTriggerLabel("manual")).toBe("You started this");
    expect(activityTriggerLabel("webhook")).toBe("From your media manager");
    expect(activityTriggerLabel(null)).toBeNull();
    expect(activityTriggerLabel("unheard_of")).toBeNull();
  });

  it("counts the newest outcome per file once", () => {
    const summary = summarizeRun([
      ev({
        id: 3,
        relative_path: "a.mkv",
        detail: '{"outcome":"ok"}',
        trigger: "retry",
      }),
      ev({ id: 2, relative_path: "a.mkv", result: "failed" }),
      ev({ id: 1, relative_path: "b.mkv", result: "failed" }),
    ]);
    expect(summary.headline).toBe(
      "Automatic retry run · 2 files: 1 processed, 1 failed",
    );
    expect(summary.failed).toBe(1);
  });

  it("falls back to entry counts when no file is named", () => {
    expect(
      summarizeRun([
        ev({ id: 2, event_type: "processing.handoff_reported" }),
        ev({ id: 1, event_type: "processing.handoff_reported" }),
      ]).headline,
    ).toBe("Run · 2 entries");
  });
});
