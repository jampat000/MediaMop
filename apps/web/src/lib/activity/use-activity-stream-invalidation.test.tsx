import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderHook, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { ReactNode } from "react";

import { activityRecentKey } from "./queries";
import { useActivityStreamInvalidation } from "./use-activity-stream-invalidation";
import { dashboardStatusKey } from "../dashboard/queries";

class FakeEventSource {
  url: string;
  listeners = new Map<string, Set<(ev: MessageEvent<string>) => void>>();
  closed = false;

  constructor(url: string) {
    this.url = url;
    FakeEventSource.instances.push(this);
  }

  addEventListener(type: string, cb: (ev: MessageEvent<string>) => void): void {
    const set = this.listeners.get(type) ?? new Set();
    set.add(cb);
    this.listeners.set(type, set);
  }

  removeEventListener(type: string, cb: (ev: MessageEvent<string>) => void): void {
    this.listeners.get(type)?.delete(cb);
  }

  close(): void {
    this.closed = true;
  }

  emit(type: string, data: string): void {
    const ev = { data } as MessageEvent<string>;
    this.listeners.get(type)?.forEach((cb) => cb(ev));
  }

  static instances: FakeEventSource[] = [];
}

function withQueryClient(qc: QueryClient) {
  return function Wrapper({ children }: { children: ReactNode }) {
    return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
  };
}

describe("useActivityStreamInvalidation", () => {
  afterEach(() => {
    FakeEventSource.instances = [];
    vi.unstubAllGlobals();
  });

  it("invalidates activity recent query on activity.latest", () => {
    vi.stubGlobal("EventSource", FakeEventSource as unknown as typeof EventSource);
    const qc = new QueryClient();
    const spy = vi.spyOn(qc, "invalidateQueries");

    renderHook(() => useActivityStreamInvalidation(activityRecentKey), {
      wrapper: withQueryClient(qc),
    });

    const src = FakeEventSource.instances[0];
    expect(src.url).toBe("/api/v1/activity/stream");
    src.emit("activity.latest", JSON.stringify({ latest_event_id: 12 }));

    expect(spy).toHaveBeenCalledWith({ queryKey: activityRecentKey });
  });

  it("invalidates when an existing activity row receives a newer revision", () => {
    vi.stubGlobal("EventSource", FakeEventSource as unknown as typeof EventSource);
    const qc = new QueryClient();
    const spy = vi.spyOn(qc, "invalidateQueries");

    renderHook(() => useActivityStreamInvalidation(activityRecentKey), {
      wrapper: withQueryClient(qc),
    });

    const src = FakeEventSource.instances[0];
    src.emit("activity.latest", JSON.stringify({ latest_event_id: 12, activity_revision: 1 }));
    src.emit("activity.latest", JSON.stringify({ latest_event_id: 12, activity_revision: 2 }));

    expect(spy).toHaveBeenCalledTimes(2);
    expect(spy).toHaveBeenLastCalledWith({ queryKey: activityRecentKey });
  });

  it("ignores malformed stream messages instead of breaking live updates", () => {
    vi.stubGlobal("EventSource", FakeEventSource as unknown as typeof EventSource);
    const qc = new QueryClient();
    const spy = vi.spyOn(qc, "invalidateQueries");

    renderHook(() => useActivityStreamInvalidation(activityRecentKey), {
      wrapper: withQueryClient(qc),
    });

    const src = FakeEventSource.instances[0];
    src.emit("activity.latest", "{");
    src.emit("activity.latest", JSON.stringify({ activity_revision: 1 }));
    src.emit("activity.latest", JSON.stringify({ latest_event_id: 12, activity_revision: 2 }));

    expect(spy).toHaveBeenCalledTimes(1);
    expect(spy).toHaveBeenCalledWith({ queryKey: activityRecentKey });
  });

  it("invalidates dashboard status query on activity.latest", () => {
    vi.stubGlobal("EventSource", FakeEventSource as unknown as typeof EventSource);
    const qc = new QueryClient();
    const spy = vi.spyOn(qc, "invalidateQueries");

    renderHook(() => useActivityStreamInvalidation(dashboardStatusKey), {
      wrapper: withQueryClient(qc),
    });

    const src = FakeEventSource.instances[0];
    src.emit("activity.latest", JSON.stringify({ latest_event_id: 77 }));

    expect(spy).toHaveBeenCalledWith({ queryKey: dashboardStatusKey });
  });

  it("shares one EventSource across multiple query subscribers", () => {
    vi.stubGlobal("EventSource", FakeEventSource as unknown as typeof EventSource);
    const qc = new QueryClient();
    const spy = vi.spyOn(qc, "invalidateQueries");

    const first = renderHook(() => useActivityStreamInvalidation(activityRecentKey), {
      wrapper: withQueryClient(qc),
    });
    const second = renderHook(() => useActivityStreamInvalidation(dashboardStatusKey), {
      wrapper: withQueryClient(qc),
    });

    expect(FakeEventSource.instances).toHaveLength(1);
    const src = FakeEventSource.instances[0];
    src.emit("activity.latest", JSON.stringify({ latest_event_id: 88 }));

    expect(spy).toHaveBeenCalledWith({ queryKey: activityRecentKey });
    expect(spy).toHaveBeenCalledWith({ queryKey: dashboardStatusKey });

    first.unmount();
    expect(src.closed).toBe(false);

    second.unmount();
    expect(src.closed).toBe(true);
  });

  it("opens a fresh EventSource after all subscribers unmount", async () => {
    vi.stubGlobal("EventSource", FakeEventSource as unknown as typeof EventSource);
    const qc = new QueryClient();

    const first = renderHook(() => useActivityStreamInvalidation(activityRecentKey), {
      wrapper: withQueryClient(qc),
    });
    first.unmount();
    await waitFor(() => expect(FakeEventSource.instances[0].closed).toBe(true));

    renderHook(() => useActivityStreamInvalidation(activityRecentKey), {
      wrapper: withQueryClient(qc),
    });

    expect(FakeEventSource.instances).toHaveLength(2);
    expect(FakeEventSource.instances[1].closed).toBe(false);
  });
});
