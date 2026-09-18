import { fireEvent, render, screen } from "@testing-library/react";
import { expect, it, vi } from "vitest";

import type { ProcessingFileLog } from "../../lib/processing/files-api";
import { FileStoryPanel } from "./file-story-panel";

function log(over: Partial<ProcessingFileLog> = {}): ProcessingFileLog {
  return {
    file_id: 1,
    relative_path: "movies/Arrival.mkv",
    retention_days: 90,
    entries: [
      {
        id: 1,
        recorded_at: "2026-09-16T14:02:00Z",
        outcome: "live_output_written",
        title: "Remuxed Arrival",
        library_name: "Films 4K",
        detail: { ffmpeg_argv: ["ffmpeg", "-c", "copy"] },
        story: [
          {
            heading: "Picked up",
            sentence: "Weir took this file as a film in the Films 4K library.",
            tone: "neutral",
          },
          {
            heading: "Planned",
            sentence:
              "Weir planned to remove 2 audio tracks. The video is copied, not re-encoded, so picture quality is unchanged.",
            tone: "neutral",
          },
          { heading: "Checked", sentence: "It was complete.", tone: "good" },
        ],
      },
    ],
    ...over,
  };
}

function mount(
  props: Partial<React.ComponentProps<typeof FileStoryPanel>> = {},
) {
  const onClose = vi.fn();
  render(
    <FileStoryPanel
      open
      fileName="Arrival.mkv"
      log={log()}
      loading={false}
      error={null}
      onClose={onClose}
      {...props}
    />,
  );
  return { onClose };
}

it("tells the story in plain steps", () => {
  mount();
  expect(
    screen.getByRole("dialog", { name: "Arrival.mkv" }),
  ).toBeInTheDocument();
  expect(screen.getByText("Picked up")).toBeInTheDocument();
  expect(screen.getByText(/copied, not re-encoded/)).toBeInTheDocument();
});

it("keeps the technical detail behind a disclosure, never leading", () => {
  mount();
  const summary = screen.getByText("Show the technical detail");
  expect(summary.closest("details")).not.toHaveAttribute("open");
});

it("says how long records are kept", () => {
  mount();
  expect(
    screen.getByText("Weir keeps these records for 90 days."),
  ).toBeInTheDocument();
});

it("closes on Escape", () => {
  const { onClose } = mount();
  fireEvent.keyDown(document, { key: "Escape" });
  expect(onClose).toHaveBeenCalledTimes(1);
});

it("closes from the backdrop and the close button", () => {
  const { onClose } = mount();
  fireEvent.click(screen.getByRole("button", { name: "Close file history" }));
  fireEvent.click(screen.getByRole("button", { name: "Close" }));
  expect(onClose).toHaveBeenCalledTimes(2);
});

it("takes focus when it opens", () => {
  mount();
  expect(screen.getByRole("dialog")).toHaveFocus();
});

it("explains an empty record rather than showing nothing", () => {
  mount({ log: log({ entries: [] }) });
  expect(
    screen.getByText(/has not worked on this file yet/),
  ).toBeInTheDocument();
});

it("shows a failure to load", () => {
  mount({
    log: undefined,
    error: "Could not read that file's processing record",
  });
  expect(screen.getByRole("alert")).toHaveTextContent("Could not read");
});

it("renders nothing while closed", () => {
  mount({ open: false });
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
});
