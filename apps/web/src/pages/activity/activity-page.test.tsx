import {
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import {
  afterEach,
  beforeAll,
  beforeEach,
  describe,
  expect,
  it,
  vi,
} from "vitest";
import type { ActivityEventItem } from "../../lib/api/types";
import { ActivityPage } from "./activity-page";

const mocks = vi.hoisted(() => ({
  useActivityRecentQuery: vi.fn(),
  role: { current: "operator" as string },
  fetchActivityExport: vi.fn(),
  fetchActivityFileHistoryPreview: vi.fn(),
  removeActivityFileHistory: vi.fn(),
  fetchSuiteOperationalHistoryPreview: vi.fn(),
  resetSuiteOperationalHistory: vi.fn(),
  fetchRefinerFiles: vi.fn(),
  fetchRefinerFileLog: vi.fn(),
}));

vi.mock("../../lib/activity/queries", () => ({
  activityRecentKey: ["activity", "recent"],
  useActivityRecentQuery: (...args: unknown[]) =>
    mocks.useActivityRecentQuery(...args),
}));

vi.mock("../../lib/activity/use-activity-stream-invalidation", () => ({
  useActivityStreamInvalidation: vi.fn(),
}));

vi.mock("../../lib/ui/mm-format-date", () => ({
  useAppDateFormatter: () => (iso: string) => iso,
}));

vi.mock("../../lib/auth/queries", () => ({
  useMeQuery: () => ({
    data: { id: 1, username: "alice", role: mocks.role.current },
  }),
}));

vi.mock("../../lib/refiner/libraries-queries", () => ({
  useRefinerLibrariesQuery: () => ({
    data: [{ id: 3, name: "Movie downloads" }],
  }),
}));

vi.mock("../../lib/api/activity-api", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../../lib/api/activity-api")>()),
  fetchActivityExport: mocks.fetchActivityExport,
  fetchActivityFileHistoryPreview: mocks.fetchActivityFileHistoryPreview,
  removeActivityFileHistory: mocks.removeActivityFileHistory,
}));

vi.mock("../../lib/suite/suite-settings-api", async (importOriginal) => ({
  ...(await importOriginal<
    typeof import("../../lib/suite/suite-settings-api")
  >()),
  fetchSuiteOperationalHistoryPreview:
    mocks.fetchSuiteOperationalHistoryPreview,
  resetSuiteOperationalHistory: mocks.resetSuiteOperationalHistory,
}));

vi.mock("../../lib/refiner/files-api", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../../lib/refiner/files-api")>()),
  fetchRefinerFiles: mocks.fetchRefinerFiles,
  fetchRefinerFileLog: mocks.fetchRefinerFileLog,
}));

beforeAll(() => {
  class EventSourceStub {
    addEventListener = vi.fn();
    removeEventListener = vi.fn();
    close = vi.fn();
  }
  vi.stubGlobal("EventSource", EventSourceStub);
});

function event(
  overrides: Partial<ActivityEventItem> & { id: number },
): ActivityEventItem {
  return {
    created_at: "2026-09-16T22:00:00Z",
    event_type: "refiner.work_temp_stale_sweep_completed",
    module: "refiner",
    title: "Temporary files cleanup finished",
    detail: null,
    trigger: null,
    result: null,
    library_id: null,
    relative_path: null,
    run_key: null,
    ...overrides,
  };
}

function recentResult(
  items: ActivityEventItem[],
  extra: Record<string, unknown> = {},
) {
  const data = {
    items,
    total: items.length,
    system_events: 0,
    has_more: false,
    retention_days: 90,
    oldest_event_at: null,
    ...extra,
  };
  return {
    isPending: false,
    isError: false,
    data,
    refetch: vi.fn(async () => ({ data })),
  };
}

function renderPage() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  const tree = () => (
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <ActivityPage />
      </MemoryRouter>
    </QueryClientProvider>
  );
  const view = render(tree());
  return { ...view, rerenderPage: () => view.rerender(tree()) };
}

function lastQueryFilters(): Record<string, unknown> {
  return mocks.useActivityRecentQuery.mock.calls.at(-1)?.[0] as Record<
    string,
    unknown
  >;
}

const fileEvent = event({
  id: 40,
  event_type: "refiner.file_remux_pass_completed",
  title: "Movie.mkv was processed successfully",
  detail: JSON.stringify({ outcome: "ok", relative_media_path: "Movie.mkv" }),
  library_id: 3,
  relative_path: "Movies/Movie.mkv",
  trigger: "webhook",
  result: "success",
});

describe("ActivityPage", () => {
  beforeEach(() => {
    mocks.role.current = "operator";
    Object.values(mocks).forEach((value) => {
      if (typeof value === "function" && "mockReset" in value)
        value.mockReset();
    });
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    class EventSourceStub {
      addEventListener = vi.fn();
      removeEventListener = vi.fn();
      close = vi.fn();
    }
    vi.stubGlobal("EventSource", EventSourceStub);
  });

  it("renders one summary line and the filters", () => {
    mocks.useActivityRecentQuery.mockReturnValue(
      recentResult([event({ id: 1, detail: '{"removed":0}' })]),
    );

    renderPage();

    expect(screen.getByTestId("activity-summary")).toHaveTextContent(
      "Showing 1 of 1 event · live",
    );
    expect(screen.getByDisplayValue("All events")).toBeInTheDocument();
    expect(screen.getByDisplayValue("Any reason")).toBeInTheDocument();
    expect(screen.getByDisplayValue("Any result")).toBeInTheDocument();
    expect(screen.getByDisplayValue("All libraries")).toBeInTheDocument();
    expect(
      screen.getAllByText("Temporary files cleanup finished").length,
    ).toBeGreaterThan(0);
  });

  it("shows a proper empty state when no events match", () => {
    mocks.useActivityRecentQuery.mockReturnValue(recentResult([]));

    renderPage();

    fireEvent.click(screen.getByRole("button", { name: "Apply filters" }));
    expect(
      screen.getByText("No activity matched the current filters."),
    ).toBeInTheDocument();
  });

  it("has no module filter, since Weir is one app", () => {
    mocks.useActivityRecentQuery.mockReturnValue(recentResult([]));

    renderPage();
    expect(screen.queryByDisplayValue("All modules")).not.toBeInTheDocument();
    expect(lastQueryFilters()).not.toHaveProperty("module");
  });

  it("folds identical consecutive entries into one row with a count", () => {
    const signIn = (id: number) =>
      event({
        id,
        event_type: "auth.login_succeeded",
        module: "auth",
        title: "Sign-in finished",
        detail: "admin",
        trigger: "manual",
      });
    mocks.useActivityRecentQuery.mockReturnValue(
      recentResult([signIn(9), signIn(8), signIn(7), event({ id: 6 })]),
    );

    renderPage();

    const rows = screen.getAllByTestId("activity-row");
    expect(rows).toHaveLength(2);
    expect(rows[0]).toHaveTextContent("Sign-in finished");
    expect(
      within(rows[0]).getByTestId("activity-repeat-count"),
    ).toHaveTextContent("×3");
    expect(screen.queryByText("System event")).not.toBeInTheDocument();
  });

  it("renders explicit labels for system repair activity", () => {
    mocks.useActivityRecentQuery.mockReturnValue(
      recentResult([
        event({
          id: 2,
          event_type: "system.reconciliation.repair",
          module: "system",
          title: "System repair action completed",
          detail: "remove_refiner_temp_artifact: Removed the temp artifact.",
        }),
      ]),
    );

    renderPage();

    expect(
      screen.getByRole("heading", { name: "System repair finished" }),
    ).toBeInTheDocument();
    expect(
      screen.getByText(
        "remove_refiner_temp_artifact: Removed the temp artifact.",
      ),
    ).toBeInTheDocument();
  });

  it("keeps long activity titles wrappable while preserving the full title", () => {
    const fileName =
      "Fantastic.Beasts.The.Secrets.of.Dumbledore.2022.UHD.BluRay.2160p.TrueHD.Atmos.FraMeSToR.mkv";
    const longTitle = `${fileName} was processed successfully`;
    mocks.useActivityRecentQuery.mockReturnValue(
      recentResult([
        event({
          id: 3,
          event_type: "refiner.file_remux_pass_completed",
          title: longTitle,
          detail: JSON.stringify({
            outcome: "ok",
            relative_media_path: fileName,
          }),
        }),
      ]),
    );

    renderPage();

    const heading = screen.getByTitle(longTitle);
    expect(heading.tagName).toBe("H2");
    expect(heading).toHaveAttribute("title", longTitle);
    expect(heading.className).toContain("[overflow-wrap:anywhere]");
  });

  it("sends trigger, result, library and file filters to the server", () => {
    mocks.useActivityRecentQuery.mockReturnValue(recentResult([]));
    renderPage();

    fireEvent.change(screen.getByDisplayValue("Any reason"), {
      target: { value: "scheduled" },
    });
    fireEvent.change(screen.getByDisplayValue("Any result"), {
      target: { value: "failed" },
    });
    fireEvent.change(screen.getByDisplayValue("All libraries"), {
      target: { value: "3" },
    });
    fireEvent.change(screen.getByPlaceholderText("Part of a file path"), {
      target: { value: "Movie.mkv" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Apply filters" }));

    expect(lastQueryFilters()).toMatchObject({
      trigger: "scheduled",
      result: "failed",
      library_id: 3,
      file: "Movie.mkv",
    });
  });

  it("applies last night as yesterday 18:00 to today 08:00 in one click", () => {
    mocks.useActivityRecentQuery.mockReturnValue(recentResult([]));
    renderPage();

    fireEvent.click(screen.getByRole("button", { name: "Last night" }));

    const filters = lastQueryFilters();
    const from = new Date(String(filters.date_from));
    const to = new Date(String(filters.date_to));
    expect(from.getHours()).toBe(18);
    expect(to.getHours()).toBe(8);
    expect(to.getTime() - from.getTime()).toBe(14 * 60 * 60 * 1000);
  });

  it("explains the trigger in plain words and shows nothing when it is not known", () => {
    mocks.useActivityRecentQuery.mockReturnValue(
      recentResult([
        fileEvent,
        event({ id: 41, trigger: null }),
        event({ id: 42, trigger: "folder_change" }),
      ]),
    );
    renderPage();

    const chips = screen.getAllByTestId("activity-trigger-chip");
    expect(chips.map((chip) => chip.textContent)).toEqual([
      "New file in watched folder",
      "From your media manager",
    ]);
  });

  it("collapses a run under one summary and expands to its entries", () => {
    const run = (
      id: number,
      path: string,
      detail: Record<string, unknown>,
      eventType = "refiner.file_remux_pass_completed",
    ) =>
      event({
        id,
        event_type: eventType,
        title: `${path} finished`,
        detail: JSON.stringify(detail),
        relative_path: path,
        run_key: "run:7",
        trigger: "scheduled",
      });
    mocks.useActivityRecentQuery.mockReturnValue(
      recentResult([
        run(20, "a.mkv", { outcome: "ok" }),
        run(19, "b.mkv", { outcome: "live_skipped_not_required" }),
        run(18, "c.mkv", {}, "refiner.file_passed_through"),
        run(17, "d.mkv", { outcome: "ok" }),
        event({
          id: 10,
          event_type: "auth.login_failed",
          module: "auth",
          title: "Sign-in failed",
        }),
        event({
          id: 9,
          event_type: "auth.login_failed",
          module: "auth",
          title: "Sign-in failed",
        }),
      ]),
    );
    renderPage();

    const runGroup = screen.getByTestId("activity-run") as HTMLDetailsElement;
    expect(runGroup).toHaveTextContent(
      "Scheduled run · 4 files: 2 processed, 1 handed back, 1 no changes needed",
    );
    expect(runGroup.open).toBe(false);
    expect(within(runGroup).getAllByTestId("activity-row")).toHaveLength(4);
    fireEvent.click(runGroup.querySelector("summary")!);
    expect(runGroup.open).toBe(true);

    const failures = screen.getByTestId("activity-cluster");
    expect(failures).toHaveTextContent("2 repeated failures");
  });

  it("states how far back history goes, with the oldest entry", () => {
    mocks.useActivityRecentQuery.mockReturnValue(
      recentResult([], {
        retention_days: 90,
        oldest_event_at: "2026-06-19T00:00:00Z",
      }),
    );
    renderPage();

    expect(screen.getByTestId("activity-retention")).toHaveTextContent(
      "History goes back 90 days (oldest entry 2026-06-19T00:00:00Z).",
    );
    expect(
      screen.getByRole("link", { name: "Change how long history is kept" }),
    ).toHaveAttribute("href", "/settings#activity-retention");
  });

  it("says history is kept until cleared when retention is 0", () => {
    mocks.useActivityRecentQuery.mockReturnValue(
      recentResult([], { retention_days: 0 }),
    );
    renderPage();

    expect(screen.getByTestId("activity-retention")).toHaveTextContent(
      "History is kept until you clear it.",
    );
  });

  it("exports the applied filters", async () => {
    mocks.useActivityRecentQuery.mockReturnValue(recentResult([]));
    mocks.fetchActivityExport.mockResolvedValue({
      blob: new Blob(["id\n"]),
      filename: "weir-activity.csv",
    });
    const createObjectURL = vi.fn(() => "blob:activity");
    vi.stubGlobal("URL", Object.assign(URL, { createObjectURL }));
    URL.revokeObjectURL = vi.fn();
    const click = vi
      .spyOn(HTMLAnchorElement.prototype, "click")
      .mockImplementation(() => undefined);
    renderPage();

    fireEvent.change(screen.getByDisplayValue("Any reason"), {
      target: { value: "scheduled" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Apply filters" }));
    fireEvent.click(screen.getByRole("button", { name: "Export CSV" }));

    await waitFor(() => expect(click).toHaveBeenCalled());
    expect(mocks.fetchActivityExport).toHaveBeenCalledWith(
      "csv",
      expect.objectContaining({ trigger: "scheduled" }),
    );
    expect(mocks.fetchActivityExport.mock.calls[0][1]).not.toHaveProperty(
      "limit",
    );

    fireEvent.click(screen.getByRole("button", { name: "Export JSON" }));
    await waitFor(() =>
      expect(mocks.fetchActivityExport).toHaveBeenCalledWith(
        "json",
        expect.objectContaining({ trigger: "scheduled" }),
      ),
    );
    click.mockRestore();
  });

  it("removes one file's history after showing the server's counts", async () => {
    const result = recentResult([fileEvent]);
    mocks.useActivityRecentQuery.mockReturnValue(result);
    mocks.fetchActivityFileHistoryPreview.mockResolvedValue({
      relative_path: "Movies/Movie.mkv",
      activity_events: 3,
      processing_records: 1,
      message:
        "This removes 3 Activity event(s) and 1 processing record(s) about Movies/Movie.mkv.",
    });
    mocks.removeActivityFileHistory.mockResolvedValue({
      relative_path: "Movies/Movie.mkv",
      activity_events_deleted: 3,
      processing_records_deleted: 1,
    });
    renderPage();

    expect(screen.getByTestId("activity-row-file")).toHaveTextContent(
      "Movie downloads · Movies/Movie.mkv",
    );
    fireEvent.click(
      screen.getByRole("button", { name: "Remove this file's history" }),
    );

    const dialog = await screen.findByTestId(
      "activity-remove-file-history-dialog",
    );
    expect(mocks.fetchActivityFileHistoryPreview).toHaveBeenCalledWith({
      relative_path: "Movies/Movie.mkv",
      library_id: 3,
    });
    expect(dialog).toHaveTextContent(
      "This removes 3 Activity event(s) and 1 processing record(s) about Movies/Movie.mkv.",
    );
    expect(dialog).toHaveTextContent("3 Activity events");
    expect(dialog).toHaveTextContent("1 processing record");
    expect(dialog).toHaveTextContent("No media file is touched.");
    expect(mocks.removeActivityFileHistory).not.toHaveBeenCalled();

    fireEvent.click(
      within(dialog).getByRole("button", { name: "Remove history" }),
    );

    await waitFor(() =>
      expect(screen.getByRole("status")).toHaveTextContent(
        "Removed 3 Activity events and 1 processing record about Movies/Movie.mkv. No media file was touched.",
      ),
    );
    expect(mocks.removeActivityFileHistory).toHaveBeenCalledWith({
      relative_path: "Movies/Movie.mkv",
      library_id: 3,
    });
    expect(result.refetch).toHaveBeenCalled();
    expect(
      screen.queryByTestId("activity-remove-file-history-dialog"),
    ).not.toBeInTheDocument();
  });

  it("clears all history only after RESET is typed, listing the counts", async () => {
    mocks.useActivityRecentQuery.mockReturnValue(recentResult([fileEvent]));
    mocks.fetchSuiteOperationalHistoryPreview.mockResolvedValue({
      status: "preview",
      activity_events_deleted: 12,
      refiner_jobs_deleted: 4,
      total_deleted: 16,
    });
    mocks.resetSuiteOperationalHistory.mockResolvedValue({
      status: "reset",
      activity_events_deleted: 12,
      refiner_jobs_deleted: 4,
      total_deleted: 16,
    });
    renderPage();

    fireEvent.click(screen.getByRole("button", { name: "Clear all history" }));
    const dialog = await screen.findByTestId(
      "activity-clear-all-history-dialog",
    );
    expect(dialog).toHaveTextContent("12 Activity events");
    expect(dialog).toHaveTextContent("4 finished jobs");
    expect(dialog).toHaveTextContent(
      "Queued and running work is kept, and so are all settings. No media file is touched.",
    );
    const confirm = within(dialog).getByRole("button", {
      name: "Clear all history",
    });
    expect(confirm).toBeDisabled();
    fireEvent.change(within(dialog).getByRole("textbox"), {
      target: { value: "reset please" },
    });
    expect(confirm).toBeDisabled();
    fireEvent.change(within(dialog).getByRole("textbox"), {
      target: { value: "RESET" },
    });
    expect(confirm).toBeEnabled();
    fireEvent.click(confirm);

    await waitFor(() =>
      expect(mocks.resetSuiteOperationalHistory).toHaveBeenCalledWith("RESET"),
    );
    await waitFor(() =>
      expect(screen.getByRole("status")).toHaveTextContent(
        "History cleared. Removed 12 Activity events and 4 finished jobs.",
      ),
    );
  });

  it("does not offer removal to viewers", () => {
    mocks.role.current = "viewer";
    mocks.useActivityRecentQuery.mockReturnValue(recentResult([fileEvent]));
    renderPage();

    expect(
      screen.getByRole("button", { name: "File story" }),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Remove this file's history" }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Clear all history" }),
    ).not.toBeInTheDocument();
  });

  it("opens the file story for the matching tracked file", async () => {
    mocks.useActivityRecentQuery.mockReturnValue(recentResult([fileEvent]));
    mocks.fetchRefinerFiles.mockResolvedValue({
      files: [
        { id: 55, library_id: 3, relative_path: "Movies/Movie.mkv.bak" },
        { id: 56, library_id: 3, relative_path: "Movies/Movie.mkv" },
      ],
      status_counts: {},
      returned: 2,
      limit: 50,
    });
    mocks.fetchRefinerFileLog.mockResolvedValue({
      file_id: 56,
      relative_path: "Movies/Movie.mkv",
      retention_days: 90,
      entries: [],
    });
    renderPage();

    fireEvent.click(screen.getByRole("button", { name: "File story" }));

    expect(await screen.findByRole("dialog")).toHaveTextContent("Movie.mkv");
    await waitFor(() =>
      expect(mocks.fetchRefinerFileLog).toHaveBeenCalledWith(56),
    );
    expect(mocks.fetchRefinerFiles).toHaveBeenCalledWith({
      library_id: 3,
      path_contains: "Movies/Movie.mkv",
      limit: 50,
    });
  });

  describe("live updates", () => {
    const older = event({ id: 5, title: "Older entry" });
    const newer = event({
      id: 6,
      event_type: "system.reconciliation.repair",
      module: "system",
      title: "Newest entry",
      detail: "Newest entry detail",
    });

    it("inserts new entries straight away when the reader is at the top", () => {
      mocks.useActivityRecentQuery.mockReturnValue(recentResult([older]));
      const view = renderPage();

      mocks.useActivityRecentQuery.mockReturnValue(
        recentResult([newer, older]),
      );
      view.rerenderPage();

      expect(screen.getByText("Newest entry detail")).toBeInTheDocument();
      expect(
        screen.queryByRole("button", { name: /new entr/ }),
      ).not.toBeInTheDocument();
    });

    it("holds new entries behind a button when the reader has scrolled away", () => {
      mocks.useActivityRecentQuery.mockReturnValue(recentResult([older]));
      const view = renderPage();
      const feed = screen.getByTestId("activity-feed");
      feed.getBoundingClientRect = () => ({ top: -240 }) as DOMRect;
      fireEvent.scroll(window);

      mocks.useActivityRecentQuery.mockReturnValue(
        recentResult([newer, older]),
      );
      view.rerenderPage();

      expect(screen.queryByText("Newest entry detail")).not.toBeInTheDocument();
      expect(screen.getAllByTestId("activity-row")).toHaveLength(1);
      fireEvent.click(
        screen.getByRole("button", { name: "1 new entry — show" }),
      );
      expect(screen.getByText("Newest entry detail")).toBeInTheDocument();
      expect(
        screen.queryByRole("button", { name: /new entr/ }),
      ).not.toBeInTheDocument();
    });

    it("holds new entries while an entry is expanded", () => {
      const detailed = event({
        id: 5,
        event_type: "refiner.custom_event",
        title: "Older entry",
        detail: "x".repeat(200),
      });
      mocks.useActivityRecentQuery.mockReturnValue(recentResult([detailed]));
      const view = renderPage();
      const details = screen
        .getByTestId("activity-feed")
        .querySelector("details")!;
      details.open = true;
      fireEvent(details, new Event("toggle"));

      mocks.useActivityRecentQuery.mockReturnValue(
        recentResult([newer, detailed]),
      );
      view.rerenderPage();

      expect(
        screen.getByRole("button", { name: "1 new entry — show" }),
      ).toBeInTheDocument();
      expect(screen.queryByText("Newest entry detail")).not.toBeInTheDocument();
    });
  });
});
