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
import { SUITE_SETTINGS_DASH_CARD_CLASS } from "./settings-shared";

const KINDS: MediaManagerKind[] = ["radarr", "sonarr", "deluno", "native"];

/** What choosing each one means, without naming what MediaMop does internally. */
const KIND_BLURBS: Record<MediaManagerKind, string> = {
  radarr: "Tells MediaMop when it has added a film.",
  sonarr: "Tells MediaMop when it has added an episode.",
  deluno:
    "Hands a file to MediaMop to work on, and waits to be told it is ready.",
  native: "Anything else that can send MediaMop a message.",
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
  // machine, so it needs the host MediaMop is actually reachable on.
  if (typeof window === "undefined") return connection.webhook_url_path;
  return `${window.location.origin}${connection.webhook_url_path}`;
}

/**
 * The same shape Subber uses for its connections: a plain headline, when it was
 * last checked, and the detail underneath. What an operator wants to know here is
 * "is it connected", not what the endpoint said.
 */
function ConnectionStatusPanel({
  connection,
  fmt,
}: {
  connection: MediaManagerConnection;
  fmt: (iso: string | null) => string;
}) {
  const headline =
    connection.last_test_ok === null
      ? "Not checked yet"
      : connection.last_test_ok
        ? "Connected"
        : "Connection failed";

  const tone =
    connection.last_test_ok === null
      ? "text-[var(--mm-text)]"
      : connection.last_test_ok
        ? "text-emerald-400"
        : "text-red-400";

  return (
    <div
      className="mt-4 rounded-md border border-[var(--mm-border)] bg-[var(--mm-card-bg)] p-3.5 text-sm text-[var(--mm-text2)]"
      data-testid="media-manager-status"
    >
      <p className={`text-sm font-medium ${tone}`}>{headline}</p>
      <p className="mt-1 text-xs text-[var(--mm-text2)]">
        Last checked:{" "}
        <span className="font-medium text-[var(--mm-text)]">
          {connection.last_test_at ? fmt(connection.last_test_at) : "never"}
        </span>
      </p>
      {connection.last_test_ok === false && connection.last_test_detail ? (
        <p className="mt-1 text-xs text-red-400">
          {connection.last_test_detail}
        </p>
      ) : null}
      {connection.last_test_ok === null ? (
        <p className="mt-2 text-xs text-[var(--mm-text2)]">
          Run a test to check MediaMop can reach it.
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
    <form onSubmit={submit} className={SUITE_SETTINGS_DASH_CARD_CLASS}>
      <div className="grid gap-3">
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
            placeholder="http://10.1.1.142:5099"
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
            MediaMop stores this safely and never shows it again.
          </span>
        </label>
      </div>

      {create.isError ? (
        <p className="mt-2 text-sm text-red-400" role="alert">
          {(create.error as Error).message}
        </p>
      ) : null}

      <div className="mt-3 flex gap-2">
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

  return (
    <div
      className={SUITE_SETTINGS_DASH_CARD_CLASS}
      data-testid="media-manager-card"
    >
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h3 className="text-base font-medium text-[var(--mm-text)]">
          {connection.name}
        </h3>
        <span className="text-xs text-[var(--mm-text2)]">
          {connection.enabled ? "Enabled" : "Disabled"}
        </span>
      </div>

      <ConnectionStatusPanel connection={connection} fmt={fmt} />

      <div className="mt-3 flex flex-wrap gap-2">
        <button
          type="button"
          data-testid="media-manager-test"
          className={mmActionButtonClass({ variant: "primary" })}
          disabled={test.isPending}
          onClick={() => test.mutate(connection.id)}
        >
          {test.isPending ? "Testing…" : "Test connection"}
        </button>
        <button
          type="button"
          className={mmActionButtonClass({ variant: "secondary" })}
          disabled={update.isPending}
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
          disabled={remove.isPending}
          onClick={() => remove.mutate(connection.id)}
        >
          Remove
        </button>
      </div>

      {/* The address and secret are needed once, when wiring the other app up.
          Folded away so the card answers "is it connected" at a glance. */}
      <details
        className="group mt-4 rounded-md border border-[var(--mm-border)] bg-black/10 px-4 py-3 text-xs text-[var(--mm-text3)]"
        data-testid="media-manager-setup-details"
      >
        <summary className="cursor-pointer list-none font-medium text-[var(--mm-text2)] marker:hidden [&::-webkit-details-marker]:hidden">
          <span className="underline-offset-2 group-open:underline">
            How to point {connection.name} at MediaMop
          </span>
        </summary>

        <div className="mt-3 border-t border-[var(--mm-border)] pt-3">
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
                Copy this into {connection.name} now — MediaMop will not show it
                again.
              </span>
            </div>
          ) : null}

          <button
            type="button"
            data-testid="media-manager-generate-secret"
            className={`mt-3 ${mmActionButtonClass({ variant: "secondary" })}`}
            disabled={secret.isPending}
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
  );
}

/** Settings: the apps that send files to MediaMop. */
export function SettingsMediaManagersTab() {
  const connections = useMediaManagerConnectionsQuery();
  const fmt = useAppDateFormatter();
  const [adding, setAdding] = useState(false);

  return (
    <div className="grid gap-4">
      <div className={mmModuleTabBlurbBandClass}>
        <p className={mmModuleTabBlurbTextClass}>
          The apps that send files to MediaMop. Connect one so MediaMop knows
          when there is something to work on.
        </p>
      </div>

      {connections.isLoading ? (
        <p className="text-sm text-[var(--mm-text2)]">Loading…</p>
      ) : null}

      {connections.data?.length === 0 && !adding ? (
        <p className="text-sm text-[var(--mm-text2)]">
          Nothing is connected yet, so no files are reaching MediaMop. Add an
          app below to get started.
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
