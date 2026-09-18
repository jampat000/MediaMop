import { useState } from "react";

import {
  MEDIA_MANAGER_KIND_LABELS,
  type MediaManagerConnection,
  type MediaManagerKind,
} from "../../lib/media-managers/media-managers-api";
import {
  useCreateMediaManagerConnection,
  useDeleteMediaManagerConnection,
  useGenerateMediaManagerWebhookSecret,
  useMediaManagerConnectionsQuery,
  useTestMediaManagerConnection,
  useUpdateMediaManagerConnection,
} from "../../lib/media-managers/queries";
import { ConfirmRemovalDialog } from "../../components/ui/confirm-removal-dialog";
import {
  mmActionButtonClass,
  mmEditableTextFieldClass,
  mmTechnicalMonoSmallClass,
} from "../../lib/ui/mm-control-roles";
import { useAppDateFormatter } from "../../lib/ui/mm-format-date";
import {
  mmModuleTabBlurbBandClass,
  mmModuleTabBlurbTextClass,
} from "../../lib/ui/mm-module-tab-blurb";
import {
  QuietFieldGroup,
  quietActionRowClass,
} from "../../components/shared/quiet-section";

const KINDS: MediaManagerKind[] = ["radarr", "sonarr", "deluno", "native"];

/** What choosing each one means, without naming what Weir does internally. */
const KIND_BLURBS: Record<MediaManagerKind, string> = {
  radarr:
    "Lets Weir check what Radarr is still importing, and download a film again.",
  sonarr:
    "Lets Weir check what Sonarr is still importing, and download an episode again.",
  deluno: "Hands a file to Weir to work on, and waits to be told it is ready.",
  native: "Anything else that can send Weir a message.",
};

type FormState = {
  kind: MediaManagerKind;
  name: string;
  base_url: string;
  api_key: string;
};

const EMPTY_FORM: FormState = {
  kind: "deluno",
  name: "",
  base_url: "",
  api_key: "",
};

function webhookUrl(connection: MediaManagerConnection): string {
  // The API returns a path, but this gets pasted into another app on another
  // machine, so it needs the host Weir is actually reachable on.
  if (typeof window === "undefined") return connection.webhook_url_path;
  return `${window.location.origin}${connection.webhook_url_path}`;
}

/**
 * A plain headline, when it was last checked, and the detail underneath. What
 * an operator wants to know here is "is it connected", not what the endpoint
 * said.
 */
function ConnectionStatusPanel({
  connection,
  fmt,
}: {
  connection: MediaManagerConnection;
  fmt: (iso: string | null) => string;
}) {
  // A result only counts with a time behind it. "Connected" above "Last checked:
  // never" is two sentences that cannot both be true, so a result with no check
  // time (a row written without one, or restored from an older install) reads as
  // unchecked rather than borrowing the success colour.
  const result = connection.last_test_at ? connection.last_test_ok : null;

  const headline =
    result === null
      ? "Not checked yet"
      : result
        ? "Connected"
        : "Connection failed";

  // The site's own status colours, so the headline reads the same in light and dark
  // as every other good/bad word in Weir, not a raw palette green and red.
  const tone =
    result === null
      ? "text-[var(--mm-text)]"
      : result
        ? "mm-status-text--healthy"
        : "mm-status-text--failed";

  return (
    <div
      className="mt-3 text-sm text-[var(--mm-text2)]"
      data-testid="media-manager-status"
    >
      <p className={`text-sm font-medium ${tone}`}>{headline}</p>
      <p className="mt-1 text-xs text-[var(--mm-text2)]">
        Last checked:{" "}
        <span className="font-medium text-[var(--mm-text)]">
          {connection.last_test_at ? fmt(connection.last_test_at) : "never"}
        </span>
      </p>
      {result === false && connection.last_test_detail ? (
        <p className="mm-status-text--failed mt-1 text-xs">
          {connection.last_test_detail}
        </p>
      ) : null}
      {result === null ? (
        <p className="mt-2 text-xs text-[var(--mm-text2)]">
          Run a test to check Weir can reach it.
        </p>
      ) : null}
    </div>
  );
}

function AddConnectionForm({ onCancel }: { onCancel: () => void }) {
  const [form, setForm] = useState<FormState>(EMPTY_FORM);
  const create = useCreateMediaManagerConnection();

  function submit(event: React.FormEvent) {
    event.preventDefault();
    create.mutate({ ...form, enabled: true }, { onSuccess: () => onCancel() });
  }

  return (
    <form onSubmit={submit}>
      <QuietFieldGroup title="Add an app">
        <div className="grid max-w-xl gap-3">
          <label className="grid gap-1 text-sm">
            <span className="text-[var(--mm-text2)]">Which app is it?</span>
            <select
              data-testid="media-manager-kind"
              className={mmEditableTextFieldClass}
              value={form.kind}
              onChange={(e) =>
                setForm({ ...form, kind: e.target.value as MediaManagerKind })
              }
            >
              {KINDS.map((kind) => (
                <option key={kind} value={kind}>
                  {MEDIA_MANAGER_KIND_LABELS[kind]}
                </option>
              ))}
            </select>
            <span className="text-xs text-[var(--mm-text2)]">
              {KIND_BLURBS[form.kind]}
            </span>
          </label>

          <label className="grid gap-1 text-sm">
            <span className="text-[var(--mm-text2)]">Name</span>
            <input
              data-testid="media-manager-name"
              className={mmEditableTextFieldClass}
              value={form.name}
              placeholder="Deluno"
              onChange={(e) => setForm({ ...form, name: e.target.value })}
            />
          </label>

          <label className="grid gap-1 text-sm">
            <span className="text-[var(--mm-text2)]">Where to find it</span>
            <input
              data-testid="media-manager-base-url"
              className={mmEditableTextFieldClass}
              value={form.base_url}
              placeholder="http://192.0.2.10:5099"
              onChange={(e) => setForm({ ...form, base_url: e.target.value })}
            />
            <span className="text-xs text-[var(--mm-text2)]">
              The address you use to open it in a browser.
            </span>
          </label>

          <label className="grid gap-1 text-sm">
            <span className="text-[var(--mm-text2)]">API key</span>
            <input
              data-testid="media-manager-api-key"
              type="password"
              className={mmEditableTextFieldClass}
              value={form.api_key}
              onChange={(e) => setForm({ ...form, api_key: e.target.value })}
            />
            <span className="text-xs text-[var(--mm-text2)]">
              Weir stores this safely and never shows it again.
            </span>
          </label>
        </div>

        {create.isError ? (
          <p className="mm-status-text--failed mt-2 text-sm" role="alert">
            {(create.error as Error).message}
          </p>
        ) : null}

        <div className={quietActionRowClass}>
          <button
            type="submit"
            data-testid="media-manager-save"
            className={mmActionButtonClass({ variant: "primary" })}
            disabled={create.isPending || !form.name.trim()}
          >
            {create.isPending ? "Adding…" : "Add"}
          </button>
          <button
            type="button"
            className={mmActionButtonClass({ variant: "secondary" })}
            onClick={onCancel}
          >
            Cancel
          </button>
        </div>
      </QuietFieldGroup>
    </form>
  );
}

function ConnectionCard({
  connection,
  fmt,
}: {
  connection: MediaManagerConnection;
  fmt: (iso: string | null) => string;
}) {
  const update = useUpdateMediaManagerConnection();
  const remove = useDeleteMediaManagerConnection();
  const test = useTestMediaManagerConnection();
  const secret = useGenerateMediaManagerWebhookSecret();
  const [revealed, setRevealed] = useState<string | null>(null);
  // Remove asks first. Nothing is deleted until the dialog is confirmed.
  const [confirmingRemoval, setConfirmingRemoval] = useState(false);
  const busy =
    update.isPending || remove.isPending || test.isPending || secret.isPending;

  return (
    <section className="mm-quiet-section" data-testid="media-manager-card">
      <div className="mm-quiet-section__head">
        <h3 className="mm-quiet-section__title">{connection.name}</h3>
        <div className="mm-quiet-section__aside">
          <span
            className={`mm-quiet-badge${connection.enabled ? "" : " mm-quiet-badge--off"}`}
          >
            {connection.enabled ? "Enabled" : "Disabled"}
          </span>
        </div>
      </div>
      <div className="mm-quiet-section__body">
        <ConnectionStatusPanel connection={connection} fmt={fmt} />

        <div className="mt-3 flex flex-wrap gap-2">
          <button
            type="button"
            data-testid="media-manager-test"
            className={mmActionButtonClass({ variant: "primary" })}
            disabled={busy}
            onClick={() => test.mutate(connection.id)}
          >
            {test.isPending ? "Testing…" : "Test connection"}
          </button>
          <button
            type="button"
            className={mmActionButtonClass({ variant: "secondary" })}
            disabled={busy}
            onClick={() =>
              update.mutate({
                id: connection.id,
                data: { enabled: !connection.enabled },
              })
            }
          >
            {connection.enabled ? "Disable" : "Enable"}
          </button>
          <button
            type="button"
            data-testid="media-manager-remove"
            className={mmActionButtonClass({ variant: "tertiary" })}
            disabled={busy}
            aria-haspopup="dialog"
            onClick={() => {
              remove.reset();
              setConfirmingRemoval(true);
            }}
          >
            Remove
          </button>
        </div>

        {confirmingRemoval ? (
          <ConfirmRemovalDialog
            testId="media-manager-remove-confirm"
            title={`Remove ${connection.name}?`}
            description={
              <>
                <p>
                  Weir will stop accepting files from {connection.name}. Its
                  address, API key and webhook secret go with it, so connecting
                  it again means setting it up from scratch.
                </p>
                <p>No media file is touched. This cannot be undone.</p>
              </>
            }
            confirmLabel="Remove connection"
            busy={remove.isPending}
            error={
              remove.isError
                ? remove.error instanceof Error
                  ? remove.error.message
                  : "Could not remove this connection."
                : null
            }
            onCancel={() => {
              remove.reset();
              setConfirmingRemoval(false);
            }}
            onConfirm={() =>
              remove.mutate(connection.id, {
                onSuccess: () => setConfirmingRemoval(false),
              })
            }
          />
        ) : null}

        {/* The address and secret are needed once, when wiring the other app up.
          Folded away so the card answers "is it connected" at a glance. */}
        <details
          className="group mt-4 border-t border-[var(--mm-border)] pt-3 text-xs text-[var(--mm-text3)]"
          data-testid="media-manager-setup-details"
        >
          {/* A disclosure has to say it opens. The browser's own triangle is hidden
            here, so the summary carries the same Show / Hide link Settings > Logs
            uses for its folded section. */}
          <summary className="flex cursor-pointer list-none items-baseline justify-between gap-3 font-medium text-[var(--mm-text2)] [&::-webkit-details-marker]:hidden">
            <span>How to point {connection.name} at Weir</span>
            <span className="mm-quiet-link group-open:hidden">Show →</span>
            <span className="mm-quiet-link hidden group-open:inline">
              Hide →
            </span>
          </summary>

          <div className="mt-3">
            {connection.kind === "sonarr" || connection.kind === "radarr" ? (
              <p
                className="mb-3 text-[var(--mm-text2)]"
                data-testid="media-manager-mapping-pointer"
              >
                {connection.name} picks up what Weir cleans through a remote
                path mapping from a library&apos;s watched folder to its output
                folder. Open that library under Processing → Libraries: its
                editor shows the exact values to enter and checks that{" "}
                {connection.name} has them.
              </p>
            ) : null}
            <p className="text-[var(--mm-text2)]">
              In {connection.name}, send files to this address:
            </p>
            <code
              className={`mt-1 block ${mmTechnicalMonoSmallClass}`}
              data-testid="media-manager-webhook-url"
            >
              {webhookUrl(connection)}
            </code>

            <p className="mt-3 text-[var(--mm-text2)]">
              {connection.webhook_secret_is_set
                ? `${connection.name} must send its secret with every file. Anything without it is ignored.`
                : `There is no secret yet, so anything on your network could send files here pretending to be ${connection.name}.`}
            </p>

            {revealed ? (
              <div
                className="mt-2 rounded bg-[var(--mm-card-bg)] p-2"
                data-testid="media-manager-secret"
              >
                <code className={mmTechnicalMonoSmallClass}>{revealed}</code>
                <span className="mt-1 block text-[var(--mm-text3)]">
                  Copy this into {connection.name} now — Weir will not show it
                  again.
                </span>
              </div>
            ) : null}

            <button
              type="button"
              data-testid="media-manager-generate-secret"
              className={`mt-3 ${mmActionButtonClass({ variant: "secondary" })}`}
              disabled={busy}
              onClick={() =>
                secret.mutate(connection.id, {
                  onSuccess: (data) => setRevealed(data.webhook_secret),
                })
              }
            >
              {connection.webhook_secret_is_set
                ? "Replace the secret"
                : "Create a secret"}
            </button>
          </div>
        </details>
      </div>
    </section>
  );
}

/** Settings: the apps that send files to Weir. */
export function SettingsMediaManagersTab() {
  const connections = useMediaManagerConnectionsQuery();
  const fmt = useAppDateFormatter();
  const [adding, setAdding] = useState(false);

  return (
    <div className="mm-quiet-stack" data-testid="suite-settings-media-managers">
      <div className={mmModuleTabBlurbBandClass}>
        <p className={mmModuleTabBlurbTextClass}>
          The apps that send files to Weir. Connect one so Weir knows when there
          is something to work on.
        </p>
      </div>

      {connections.isLoading ? <p className="mm-quiet-note">Loading…</p> : null}

      {connections.data?.length === 0 && !adding ? (
        <p className="mm-quiet-note">
          Nothing is connected yet, so no files are reaching Weir. Add an app
          below to get started.
        </p>
      ) : null}

      {connections.data?.map((connection) => (
        <ConnectionCard key={connection.id} connection={connection} fmt={fmt} />
      ))}

      {adding ? (
        <AddConnectionForm onCancel={() => setAdding(false)} />
      ) : (
        <div>
          <button
            type="button"
            data-testid="media-manager-add"
            className={mmActionButtonClass({ variant: "primary" })}
            onClick={() => setAdding(true)}
          >
            Add an app
          </button>
        </div>
      )}
    </div>
  );
}
