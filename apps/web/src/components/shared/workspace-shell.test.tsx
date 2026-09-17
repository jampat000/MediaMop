import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import {
  WorkspacePage,
  WorkspacePanel,
  WorkspaceTabList,
} from "./workspace-shell";

describe("workspace shell", () => {
  it("connects the themed horizontal tabs to their shared panel", () => {
    const onSelect = vi.fn();

    render(
      <WorkspacePage
        eyebrow="Weir"
        title="Example"
        description="Example sections"
      >
        <WorkspaceTabList
          tabs={[
            { id: "overview", label: "Overview" },
            { id: "jobs", label: "Jobs" },
          ]}
          activeId="overview"
          onSelect={onSelect}
          ariaLabel="Example sections"
          idPrefix="example-tab"
          panelId="example-panel"
        />
        <WorkspacePanel
          id="example-panel"
          labelledBy="example-tab-overview"
          context="What this tab does."
        >
          <p>Panel content</p>
        </WorkspacePanel>
      </WorkspacePage>,
    );

    expect(screen.getByRole("heading", { name: "Example" })).toBeVisible();
    expect(
      screen.getByRole("tablist", { name: "Example sections" }),
    ).toHaveClass("mm-workspace-tabs__list");
    expect(screen.getByRole("tab", { name: "Overview" })).toHaveAttribute(
      "aria-controls",
      "example-panel",
    );
    expect(screen.getByRole("tabpanel")).toHaveAttribute(
      "aria-labelledby",
      "example-tab-overview",
    );

    fireEvent.click(screen.getByRole("tab", { name: "Jobs" }));
    expect(onSelect).toHaveBeenCalledWith("jobs");
  });
});
