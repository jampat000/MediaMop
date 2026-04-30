import { type ReactNode, useEffect, useState } from "react";

type ReadyStep = {
  name: string;
  status: "ready" | "starting" | "failed" | string;
  detail: string;
};

type ReadyPayload = {
  ready: boolean;
  status: string;
  startup_seconds: number;
  steps: ReadyStep[];
};

type StartupState =
  | { kind: "starting"; message: string; steps: ReadyStep[]; elapsedMs: number }
  | { kind: "ready" }
  | { kind: "failed"; message: string; steps: ReadyStep[] };

const READY_PATH = "/ready";
const POLL_MS = 1000;
const STARTUP_TIMEOUT_MS = 60_000;

async function fetchReadiness(signal: AbortSignal): Promise<ReadyPayload> {
  const response = await fetch(READY_PATH, {
    method: "GET",
    headers: { Accept: "application/json" },
    cache: "no-store",
    signal,
  });
  const payload = (await response.json()) as ReadyPayload;
  if (!response.ok && !payload.ready) {
    return payload;
  }
  return payload;
}

export function StartupGate({ children }: { children: ReactNode }) {
  const [state, setState] = useState<StartupState>({
    kind: "starting",
    message: "Starting MediaMop...",
    steps: [],
    elapsedMs: 0,
  });

  useEffect(() => {
    let cancelled = false;
    const startedAt = Date.now();
    let timer: number | undefined;

    const poll = async () => {
      const controller = new AbortController();
      try {
        const payload = await fetchReadiness(controller.signal);
        if (cancelled) {
          return;
        }
        if (payload.ready) {
          setState({ kind: "ready" });
          return;
        }
        const elapsedMs = Date.now() - startedAt;
        if (elapsedMs >= STARTUP_TIMEOUT_MS) {
          setState({
            kind: "failed",
            message:
              "MediaMop did not become ready in time. Check that the MediaMop server is still running, then refresh.",
            steps: payload.steps ?? [],
          });
          return;
        }
        setState({
          kind: "starting",
          message: "Starting MediaMop...",
          steps: payload.steps ?? [],
          elapsedMs,
        });
        timer = window.setTimeout(poll, POLL_MS);
      } catch {
        if (cancelled) {
          return;
        }
        const elapsedMs = Date.now() - startedAt;
        if (elapsedMs >= STARTUP_TIMEOUT_MS) {
          setState({
            kind: "failed",
            message:
              "MediaMop did not respond in time. Check that the MediaMop server is running, then refresh.",
            steps: [],
          });
          return;
        }
        setState({
          kind: "starting",
          message: "Starting MediaMop...",
          steps: [
            {
              name: "server",
              status: "starting",
              detail: "Waiting for the MediaMop server to answer.",
            },
          ],
          elapsedMs,
        });
        timer = window.setTimeout(poll, POLL_MS);
      }
    };

    void poll();
    return () => {
      cancelled = true;
      if (timer !== undefined) {
        window.clearTimeout(timer);
      }
    };
  }, []);

  if (state.kind === "ready") {
    return <>{children}</>;
  }

  return (
    <main className="min-h-screen bg-[var(--mm-bg)] px-6 py-10 text-[var(--mm-text)]">
      <div className="mx-auto flex min-h-[70vh] max-w-xl flex-col justify-center">
        <p className="text-xs font-semibold uppercase tracking-[0.28em] text-[var(--mm-accent)]">
          MediaMop
        </p>
        <h1 className="mt-4 text-3xl font-semibold">{state.message}</h1>
        <p className="mt-3 text-sm leading-6 text-[var(--mm-text3)]">
          Preparing the local database, background workers, and schedules before
          opening the app.
        </p>
        <div className="mt-6 rounded border border-[var(--mm-border)] bg-[var(--mm-card-bg)] p-4">
          <div className="h-2 overflow-hidden rounded-full bg-[var(--mm-input-bg)]">
            <div
              className="h-full rounded-full bg-[var(--mm-accent)] transition-all"
              style={{
                width:
                  state.kind === "failed"
                    ? "100%"
                    : `${Math.min(90, 20 + state.elapsedMs / 750)}%`,
              }}
            />
          </div>
          <ul className="mt-4 space-y-3 text-sm">
            {(state.steps.length
              ? state.steps
              : [
                  {
                    name: "server",
                    status: "starting",
                    detail: "Waiting for MediaMop to start.",
                  },
                ]
            ).map((step) => (
              <li key={step.name} className="flex gap-3">
                <span
                  className={
                    step.status === "ready"
                      ? "mt-1 h-2.5 w-2.5 rounded-full bg-emerald-400"
                      : state.kind === "failed"
                        ? "mt-1 h-2.5 w-2.5 rounded-full bg-red-400"
                        : "mt-1 h-2.5 w-2.5 rounded-full bg-[var(--mm-accent)]"
                  }
                />
                <span>
                  <span className="block font-semibold capitalize text-[var(--mm-text)]">
                    {step.name}
                  </span>
                  <span className="text-[var(--mm-text3)]">{step.detail}</span>
                </span>
              </li>
            ))}
          </ul>
        </div>
        {state.kind === "failed" ? (
          <button
            type="button"
            className="mt-5 w-fit rounded border border-[var(--mm-accent)] bg-[var(--mm-accent)] px-4 py-2 text-sm font-semibold text-black"
            onClick={() => window.location.reload()}
          >
            Try again
          </button>
        ) : null}
      </div>
    </main>
  );
}
