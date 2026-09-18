import { fireEvent, render, screen } from "@testing-library/react";
import { expect, it, vi } from "vitest";

import { ChooseTracksPanel } from "./choose-tracks-panel";
import type { ProcessingFileTracks } from "../../lib/processing/files-api";

function tracks(
  over: Partial<ProcessingFileTracks> = {},
): ProcessingFileTracks {
  return {
    file_id: 1,
    relative_path: "Some Film/film.mkv",
    media_scope: "movie",
    source_fingerprint: {
      device: 0,
      inode: 0,
      size_bytes: 100,
      modified_time_ns: 1,
    },
    streams: [
      {
        index: 0,
        type: "video",
        codec: "h264",
        language: null,
        title: null,
        channels: null,
        default: true,
        forced: false,
        rule_would_keep: true,
        rule_reason: "Kept as the video track.",
      },
      {
        index: 1,
        type: "audio",
        codec: "aac",
        language: "eng",
        title: null,
        channels: 2,
        default: true,
        forced: false,
        rule_would_keep: true,
        rule_reason: "Kept: selected as the best audio track.",
      },
      {
        index: 2,
        type: "audio",
        codec: "aac",
        language: "jpn",
        title: null,
        channels: 2,
        default: false,
        forced: false,
        rule_would_keep: false,
        rule_reason: "Removed: not selected.",
      },
      {
        index: 3,
        type: "subtitle",
        codec: "subrip",
        language: "eng",
        title: null,
        channels: null,
        default: false,
        forced: false,
        rule_would_keep: false,
        rule_reason: "Removed: the saved rules remove every subtitle track.",
      },
    ],
    ...over,
  };
}

function baseProps() {
  return {
    open: true,
    fileName: "Some Film/film.mkv",
    tracks: tracks(),
    loading: false,
    loadError: null,
    submitting: false,
    submitError: null,
    onClose: vi.fn(),
    onSubmit: vi.fn(),
  };
}

it("renders nothing when closed", () => {
  const { container } = render(
    <ChooseTracksPanel {...baseProps()} open={false} />,
  );
  expect(container).toBeEmptyDOMElement();
});

it("seeds each row from what the saved rules would do", () => {
  render(<ChooseTracksPanel {...baseProps()} />);

  expect(screen.getByTestId("choose-tracks-keep-0")).toBeChecked();
  expect(screen.getByTestId("choose-tracks-keep-1")).toBeChecked();
  expect(screen.getByTestId("choose-tracks-keep-2")).not.toBeChecked();
  expect(screen.getByTestId("choose-tracks-keep-3")).not.toBeChecked();
  // The dropped section lists exactly what is not kept at the start.
  const dropped = screen.getByTestId("choose-tracks-dropped-list");
  expect(dropped).toHaveTextContent("jpn");
  expect(dropped).toHaveTextContent("eng");
});

it("refuses to submit with no video kept", () => {
  render(<ChooseTracksPanel {...baseProps()} />);

  fireEvent.click(screen.getByTestId("choose-tracks-keep-0"));

  expect(
    screen.getByText("Keep at least one video track."),
  ).toBeInTheDocument();
  expect(screen.getByTestId("choose-tracks-submit")).toBeDisabled();
});

it("refuses to submit with no audio kept", () => {
  render(<ChooseTracksPanel {...baseProps()} />);

  fireEvent.click(screen.getByTestId("choose-tracks-keep-1"));

  expect(
    screen.getByText("Keep at least one audio track."),
  ).toBeInTheDocument();
  expect(screen.getByTestId("choose-tracks-submit")).toBeDisabled();
});

it("moves a kept track earlier and later with the order buttons", () => {
  render(<ChooseTracksPanel {...baseProps()} />);

  // Keep the Japanese track too, so there is something to reorder against the English one.
  fireEvent.click(screen.getByTestId("choose-tracks-keep-2"));
  const order = screen.getAllByTestId(/^choose-tracks-order-/);
  expect(order.map((row) => row.dataset.testid)).toEqual([
    "choose-tracks-order-0",
    "choose-tracks-order-1",
    "choose-tracks-order-2",
  ]);

  fireEvent.click(screen.getByTestId("choose-tracks-move-up-2"));

  const reordered = screen.getAllByTestId(/^choose-tracks-order-/);
  expect(reordered.map((row) => row.dataset.testid)).toEqual([
    "choose-tracks-order-0",
    "choose-tracks-order-2",
    "choose-tracks-order-1",
  ]);
});

it("submits exactly the kept indices, their flags and the chosen order", () => {
  const onSubmit = vi.fn();
  render(<ChooseTracksPanel {...baseProps()} onSubmit={onSubmit} />);

  fireEvent.click(screen.getByTestId("choose-tracks-submit"));

  expect(onSubmit).toHaveBeenCalledWith({
    keep: [
      { index: 0, default: false, forced: false },
      { index: 1, default: true, forced: false },
    ],
    order: [0, 1],
  });
});

it("marking a different audio track default clears the previous one", () => {
  const onSubmit = vi.fn();
  render(<ChooseTracksPanel {...baseProps()} onSubmit={onSubmit} />);
  fireEvent.click(screen.getByTestId("choose-tracks-keep-2"));

  fireEvent.click(screen.getByTestId("choose-tracks-default-2"));
  fireEvent.click(screen.getByTestId("choose-tracks-submit"));

  const call = onSubmit.mock.calls[0][0] as {
    keep: { index: number; default: boolean }[];
  };
  const byIndex = new Map(call.keep.map((k) => [k.index, k.default]));
  expect(byIndex.get(1)).toBe(false);
  expect(byIndex.get(2)).toBe(true);
});

it("shows the load error instead of a table when the probe failed", () => {
  render(
    <ChooseTracksPanel
      {...baseProps()}
      tracks={undefined}
      loadError="Weir could not read this file's tracks."
    />,
  );

  expect(
    screen.getByText("Weir could not read this file's tracks."),
  ).toBeInTheDocument();
  expect(screen.queryByRole("table")).not.toBeInTheDocument();
});
