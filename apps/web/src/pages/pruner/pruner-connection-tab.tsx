import { Link, useOutletContext } from "react-router-dom";
import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { useMeQuery } from "../../lib/auth/queries";
import { postPrunerConnectionTest } from "../../lib/pruner/api";
import type { PrunerServerInstance } from "../../lib/pruner/api";
import { formatPrunerDateTime } from "./pruner-ui-utils";

type Ctx = { instanceId: number; instance: PrunerServerInstance | undefined };

export function PrunerConnectionTab(props: { contextOverride?: Ctx }) {
  const outletCtx = useOutletContext<Ctx>();
  const { instanceId, instance } = props.contextOverride ?? outletCtx;
  const me = useMeQuery();
  const qc = useQueryClient();
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const canOperate = me.data?.role === "admin" || me.data?.role === "operator";

  async function runTest() {
    setErr(null);
    setMsg(null);
    setBusy(true);
    try {
      const { pruner_job_id } = await postPrunerConnectionTest(instanceId);
      await qc.invalidateQueries({
        queryKey: ["pruner", "instances", instanceId],
      });
      setMsg(
        `Connection test started. When it finishes, this panel and Activity update for this server only (task #${pruner_job_id}).`,
      );
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div
      className="mm-bubble-stack max-w-3xl"
      data-testid="pruner-connection-tab"
    >
      <header className="mm-page__intro !mb-0 border-0 p-0 shadow-none">
        <p className="mm-page__eyebrow">This server</p>
        <h2 className="mm-page__title text-xl sm:text-2xl">Connection</h2>
        <p className="mm-page__subtitle max-w-3xl">
          Check that MediaMop can reach{" "}
          <strong className="text-[var(--mm-text)]">this</strong> server only.
          Jellyfin and Emby use a small public info check; Plex checks identity
          with your saved token when you have one.
        </p>
      </header>

      <section
        className="rounded-md border border-[var(--mm-border)] bg-[var(--mm-card-bg)] px-4 py-4 text-sm text-[var(--mm-text2)]"
        aria-labelledby="pruner-conn-status"
      >
        <h3
          id="pruner-conn-status"
          className="text-sm font-semibold text-[var(--mm-text1)]"
        >
          Last completed test
        </h3>
        {instance ? (
          <dl className="mt-3 space-y-2 text-xs sm:text-sm">
            <div className="flex flex-wrap gap-x-2">
              <dt className="text-[var(--mm-text3)]">When</dt>
              <dd className="font-medium text-[var(--mm-text1)]">
                {formatPrunerDateTime(instance.last_connection_test_at)}
              </dd>
            </div>
            <div className="flex flex-wrap gap-x-2">
              <dt className="text-[var(--mm-text3)]">OK</dt>
              <dd className="font-medium text-[var(--mm-text1)]">
                {instance.last_connection_test_ok === null
                  ? "—"
                  : instance.last_connection_test_ok
                    ? "Yes"
                    : "No"}
              </dd>
            </div>
            <div>
              <dt className="text-[var(--mm-text3)]">Detail</dt>
              <dd className="mt-0.5 text-[var(--mm-text2)]">
                {instance.last_connection_test_detail ?? "—"}
              </dd>
            </div>
          </dl>
        ) : (
          <p className="mt-2 text-xs text-[var(--mm-text2)]">Loading server…</p>
        )}
      </section>

      {canOperate ? (
        <button
          type="button"
          className="rounded-md bg-[var(--mm-accent)] px-3 py-1.5 text-sm font-medium text-white disabled:opacity-50"
          disabled={busy}
          onClick={() => void runTest()}
        >
          Run connection test
        </button>
      ) : (
        <p className="text-sm text-[var(--mm-text2)]">
          Sign in as an operator to run connection tests.
        </p>
      )}
      {err ? (
        <p className="text-sm text-red-600" role="alert">
          {err}
        </p>
      ) : null}
      {msg ? <p className="text-sm text-[var(--mm-text)]">{msg}</p> : null}

      <p className="text-xs text-[var(--mm-text2)]">
        Job outcomes:{" "}
        <Link
          className="font-semibold text-[var(--mm-accent)] underline-offset-2 hover:underline"
          to="/activity"
        >
          Activity
        </Link>
      </p>
    </div>
  );
}
