import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { AppErrorScreen, ErrorBoundary } from "./error-boundary";

function BrokenRoute() {
  throw new Error("Route render failed");
  return null;
}

describe("ErrorBoundary", () => {
  const preventExpectedRenderError = (event: ErrorEvent) => {
    if (event.error?.message === "Route render failed") {
      event.preventDefault();
    }
  };

  beforeEach(() => {
    vi.spyOn(console, "error").mockImplementation(() => undefined);
    window.addEventListener("error", preventExpectedRenderError);
  });

  afterEach(() => {
    window.removeEventListener("error", preventExpectedRenderError);
    vi.restoreAllMocks();
  });

  it("renders the recovery screen when a child throws", () => {
    render(
      <ErrorBoundary>
        <BrokenRoute />
      </ErrorBoundary>,
    );

    expect(screen.getByRole("heading", { name: "Something went wrong" })).toBeInTheDocument();
    expect(screen.getByText("Route render failed")).toBeInTheDocument();
    expect(screen.getByRole("navigation", { name: "Unavailable sections" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Reload MediaMop" })).toBeInTheDocument();
  });

  it("lets the user trigger reload from the fallback", () => {
    const onReload = vi.fn();
    render(<AppErrorScreen error={new Error("Bad route state")} onReload={onReload} />);

    fireEvent.click(screen.getByRole("button", { name: "Reload MediaMop" }));

    expect(onReload).toHaveBeenCalledTimes(1);
  });
});
