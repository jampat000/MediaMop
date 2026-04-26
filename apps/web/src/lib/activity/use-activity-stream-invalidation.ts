import { useEffect } from "react";
import { useQueryClient, type QueryKey } from "@tanstack/react-query";

type LatestPayload = { latest_event_id: number; activity_revision?: number };
type ActivityLatestSubscriber = () => void;

let source: EventSource | null = null;
const subscribers = new Set<ActivityLatestSubscriber>();

function emitActivityLatest(): void {
  subscribers.forEach((subscriber) => subscriber());
}

function parseLatestPayload(data: string): LatestPayload | null {
  try {
    const parsed = JSON.parse(data) as Partial<LatestPayload>;
    if (typeof parsed.latest_event_id !== "number") {
      return null;
    }
    return { latest_event_id: parsed.latest_event_id };
  } catch {
    return null;
  }
}

function ensureActivityStream(): EventSource | null {
  if (source) {
    return source;
  }
  if (typeof EventSource === "undefined") {
    return null;
  }
  source = new EventSource("/api/v1/activity/stream");
  source.addEventListener("activity.latest", (ev) => {
    const payload = parseLatestPayload((ev as MessageEvent<string>).data);
    if (!payload) {
      return;
    }
    emitActivityLatest();
  });
  return source;
}

function subscribeActivityLatest(subscriber: ActivityLatestSubscriber): () => void {
  subscribers.add(subscriber);
  ensureActivityStream();

  return () => {
    subscribers.delete(subscriber);
    if (subscribers.size === 0) {
      source?.close();
      source = null;
    }
  };
}

export function useActivityStreamInvalidation(queryKey: QueryKey): void {
  const qc = useQueryClient();

  useEffect(() => {
    return subscribeActivityLatest(() => {
      void qc.invalidateQueries({ queryKey });
    });
  }, [qc, queryKey]);
}

export function useActivityStreamInvalidations(queryKeys: readonly QueryKey[]): void {
  const qc = useQueryClient();

  useEffect(() => {
    return subscribeActivityLatest(() => {
      queryKeys.forEach((queryKey) => {
        void qc.invalidateQueries({ queryKey });
      });
    });
  }, [qc, queryKeys]);
}
