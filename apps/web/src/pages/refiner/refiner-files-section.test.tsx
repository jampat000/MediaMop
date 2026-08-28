import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, expect, it, vi } from "vitest";

import * as api from "../../lib/refiner/files-api";
import type {
  RefinerFile,
  RefinerFilesPage,
} from "../../lib/refiner/files-api";
import * as librariesApi from "../../lib/refiner/libraries-api";
import * as authQueries from "../../lib/auth/queries";
import { RefinerFilesSection } from "./refiner-files-section";

function file(over: Partial<RefinerFile> = {}): RefinerFile {
  return {
    id: 1,
    library_id: 1,
    library_name: "Movies",
    relative_path: "Some Film/film.mkv",
    status: "unprocessed",
    status_reason: "Ready for Refiner to process as part of Movies.",
    blocked_by_connection: null,
    size_bytes: 2048,
    last_seen_at: null,
    last_attempt_at: null,
    ...over,
  };
}

function page(over: Partial<RefinerFilesPage> = {}): RefinerFilesPage {
  return {
    files: [file()],
    status_counts: { unprocessed: 1, on_hold: 0, blocked_upstream: 0 },
    returned: 1,
    limit: 200,
    ...over,
  };
}

function wrapper({ children }: { children: ReactNode }) {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
}

function asOperator() {
  vi.spyOn(authQueries, "useMeQuery").mockReturnValue({
    data: { role: "operator" },
  } as ReturnType<typeof authQueries.useMeQuery>);
  vi.spyOn(librariesApi, "fetchRefinerLibraries").mockResolvedValue([]);
}

afterEach(() => {
  vi.restoreAllMocks();
});

it("shows the reason a file is not being processed", async () => {
  asOperator();
  vi.spyOn(api, "fetchRefinerFiles").mockResolvedValue(
    page({
      files: [
        file({
          status: "blocked_upstream",
          status_reason:
            "Deluno (Main) is still importing this file, so MediaMop left it alone for now.",
          blocked_by_connection: "Deluno (Main)",
        }),
      ],
      status_counts: { blocked_upstream: 1 },
    }),
  );

  render(<RefinerFilesSection />, { wrapper });

  expect(
    await screen.findByText(/Deluno \(Main\) is still importing this file/),
  ).toBeInTheDocument();
});

it("shows a bucket for every state, including empty ones", async () => {
  asOperator();
  vi.spyOn(api, "fetchRefinerFiles").mockResolvedValue(page());

  render(<RefinerFilesSection />, { wrapper });

  expect(
    await screen.findByTestId("refiner-files-bucket-on_hold"),
  ).toHaveTextContent("On hold (0)");
  expect(
    screen.getByTestId("refiner-files-bucket-out_of_schedule"),
  ).toBeInTheDocument();
  expect(
    screen.getByTestId("refiner-files-bucket-disabled"),
  ).toBeInTheDocument();
});

it("filters by bucket", async () => {
  asOperator();
  const fetchFiles = vi
    .spyOn(api, "fetchRefinerFiles")
    .mockResolvedValue(page());

  render(<RefinerFilesSection />, { wrapper });
  fireEvent.click(await screen.findByTestId("refiner-files-bucket-on_hold"));

  await waitFor(() => {
    expect(fetchFiles).toHaveBeenCalledWith(
      expect.objectContaining({ file_status: "on_hold" }),
    );
  });
});

it("says removing a file only removes the record", async () => {
  asOperator();
  vi.spyOn(api, "fetchRefinerFiles").mockResolvedValue(page());

  render(<RefinerFilesSection />, { wrapper });

  const button = await screen.findByTestId("refiner-file-forget-1");
  expect(button).toHaveAttribute(
    "title",
    expect.stringContaining("file on disk is untouched"),
  );
});

it("does not offer removal to a viewer", async () => {
  vi.spyOn(authQueries, "useMeQuery").mockReturnValue({
    data: { role: "viewer" },
  } as ReturnType<typeof authQueries.useMeQuery>);
  vi.spyOn(librariesApi, "fetchRefinerLibraries").mockResolvedValue([]);
  vi.spyOn(api, "fetchRefinerFiles").mockResolvedValue(page());

  render(<RefinerFilesSection />, { wrapper });

  expect(await screen.findByText("Some Film/film.mkv")).toBeInTheDocument();
  expect(screen.queryByTestId("refiner-file-forget-1")).not.toBeInTheDocument();
});

it("explains an empty list rather than showing nothing", async () => {
  asOperator();
  vi.spyOn(api, "fetchRefinerFiles").mockResolvedValue(
    page({ files: [], status_counts: {}, returned: 0 }),
  );

  render(<RefinerFilesSection />, { wrapper });

  expect(await screen.findByText(/No files match/)).toBeInTheDocument();
});
