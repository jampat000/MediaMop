import { fireEvent, render, screen } from "@testing-library/react";
import { expect, it, vi } from "vitest";

import { ScheduleGridEditor } from "./schedule-grid-editor";

const SLOTS_PER_WEEK = 7 * 24 * 4;

it("treats an empty grid as no restriction rather than as never", () => {
  render(<ScheduleGridEditor value="" onChange={vi.fn()} />);

  expect(screen.getByTestId("schedule-grid")).toHaveTextContent(
    /runs at any time/i,
  );
});

it("writes all four quarters of an hour, so nothing is lost in the round trip", () => {
  const onChange = vi.fn();
  render(
    <ScheduleGridEditor
      value={"0".repeat(SLOTS_PER_WEEK)}
      onChange={onChange}
    />,
  );

  // Wednesday (day 2) at 14:00.
  fireEvent.pointerDown(screen.getByTestId("schedule-cell-2-14"));

  const written: string = onChange.mock.calls[0][0];
  const start = 2 * 96 + 14 * 4;
  expect(written.slice(start, start + 4)).toBe("1111");
  expect(written).toHaveLength(SLOTS_PER_WEEK);
});

it("turns an hour back off", () => {
  const onChange = vi.fn();
  render(
    <ScheduleGridEditor
      value={"1".repeat(SLOTS_PER_WEEK)}
      onChange={onChange}
    />,
  );

  fireEvent.pointerDown(screen.getByTestId("schedule-cell-0-9"));

  const written: string = onChange.mock.calls[0][0];
  expect(written.slice(9 * 4, 9 * 4 + 4)).toBe("0000");
});

it("clears back to an empty grid rather than an all-zero one", () => {
  const onChange = vi.fn();
  render(
    <ScheduleGridEditor
      value={"0".repeat(SLOTS_PER_WEEK)}
      onChange={onChange}
    />,
  );

  fireEvent.click(screen.getByTestId("schedule-clear"));

  // "" means any time; "000…" would mean never, and confusing the two would stop all work.
  expect(onChange).toHaveBeenCalledWith("");
});

it("can select nothing at all, which is a different thing from no schedule", () => {
  const onChange = vi.fn();
  render(<ScheduleGridEditor value="" onChange={onChange} />);

  fireEvent.click(screen.getByTestId("schedule-none"));

  expect(onChange).toHaveBeenCalledWith("0".repeat(SLOTS_PER_WEEK));
});

it("draws a malformed grid as unrestricted instead of inventing a schedule", () => {
  render(<ScheduleGridEditor value="not-a-grid" onChange={vi.fn()} />);

  expect(screen.getByTestId("schedule-cell-3-12")).toHaveAttribute(
    "aria-pressed",
    "true",
  );
});

it("does not let a viewer change the grid", () => {
  const onChange = vi.fn();
  render(<ScheduleGridEditor value="" onChange={onChange} disabled />);

  fireEvent.pointerDown(screen.getByTestId("schedule-cell-1-8"));

  expect(onChange).not.toHaveBeenCalled();
});
