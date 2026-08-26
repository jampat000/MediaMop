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
} from "../../lib/ui/mm-control-roles";
import {
  mmModuleTabBlurbBandClass,
  mmModuleTabBlurbTextClass,
} from "../../lib/ui/mm-module-tab-blurb";
import { SUITE_SETTINGS_DASH_CARD_CLASS } from "./settings-shared";

const KINDS: MediaManagerKind[] = ["radarr", "sonarr", "deluno", "native"];

/** What each kind is for, in one line, so the picker is not just four names. */
const KIND_BLURBS: Record<MediaManagerKind, string> = {
  radarr:
    "Tells MediaMop when it has added a film, so subtitles can be found for it.",
  sonarr:
    "Tells MediaMop when it has added an episode, so subtitles can be found for it.",
  deluno:
    "Passes a finished download to MediaMop to clean up first, and waits to be told the tidied file is ready.",
  native:
    "Anything else that can send MediaMop a message. Use this if your app is not listed.",
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
  // The API returns a path, but the operator has to paste this into another app on
  // another machine, so it needs the host MediaMop is actually reachable on.
  if (typeof window === "undefined") return connection.webhook_url_path;
  return `${window.location.origin}${connection.webhook_url_path}`;
}

function testTone(connection: MediaManagerConnection): string {
  if (connection.last_test_ok === true) return "text-emerald-400";
  if (connection.last_test_ok === false) return "text-red-400";
  return "text-[var(--mm-text2)]";
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
            The address you use to open this app in a browser. MediaMop uses it
            to check the app is there, and to tell it when work is finished.
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
}: {
  connection: MediaManagerConnection;
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
        <div>
          <h3 className="text-base font-medium text-[var(--mm-text)]">
            {connection.name}
          </h3>
          <p className="text-xs text-[var(--mm-text2)]">
            {MEDIA_MANAGER_KIND_LABELS[connection.kind]} ·{" "}
            {connection.base_url || "no address yet"}
          </p>
        </div>
        <span className="text-xs text-[var(--mm-text2)]">
          {connection.enabled ? "Enabled" : "Disabled"}
        </span>
      </div>

      {connection.last_test_detail ? (
        <p className={`mt-2 text-sm ${testTone(connection)}`}>
          {connection.last_test_detail}
        </p>
      ) : null}

      <div className="mt-3 rounded-md border border-[var(--mm-border)] p-3">
        <p className="text-sm text-[var(--mm-text)]">
          Tell {connection.name} to send its files here
        </p>
        <code
          className="mt-1 block break-all text-xs text-[var(--mm-text2)]"
          data-testid="media-manager-webhook-url"
        >
          {webhookUrl(connection)}
        </code>
        <p className="mt-1 text-xs text-[var(--mm-text2)]">
          Copy this into {connection.name}, so it knows where to send a file
          when it wants MediaMop to work on one.
        </p>
        {connection.webhook_secret_is_set ? (
          <p className="mt-2 text-xs text-[var(--mm-text2)]">
            {connection.name} also has to send its secret with every file.
            Anything that turns up without it is ignored.
          </p>
        ) : (
          <p className="mt-2 text-xs text-[var(--mm-text2)]">
            There is no secret yet, so anything on your network could send files
            here pretending to be {connection.name}. Generate one below and
            paste it into {connection.name} as well.
          </p>
        )}
        {revealed ? (
          <div
            className="mt-2 rounded bg-[var(--mm-card-bg)] p-2 text-xs"
            data-testid="media-manager-secret"
          >
            <code className="block break-all text-[var(--mm-text)]">
              {revealed}
            </code>
            <span className="mt-1 block text-[var(--mm-text2)]">
              Copy this into {connection.name} now — MediaMop will not show it
              again.
            </span>
          </div>
        ) : null}
      </div>

      <div className="mt-3 flex flex-wrap gap-2">
        <button
          type="button"
          data-testid="media-manager-test"
          className={mmActionButtonClass({ variant: "secondary" })}
          disabled={test.isPending}
          onClick={() => test.mutate(connection.id)}
        >
          {test.isPending ? "Testing…" : "Test"}
        </button>
        <button
          type="button"
          data-testid="media-manager-generate-secret"
          className={mmActionButtonClass({ variant: "secondary" })}
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
    </div>
  );
}

/** Settings: the media managers MediaMop accepts work from and reports back to. */
export function SettingsMediaManagersTab() {
  const connections = useMediaManagerConnectionsQuery();
  const [adding, setAdding] = useState(false);

  return (
    <div className="grid gap-4">
      <div className={mmModuleTabBlurbBandClass}>
        <p className={mmModuleTabBlurbTextClass}>
          These are the apps that send files to MediaMop. Radarr and Sonarr tell
          MediaMop when they have added something, so it can go and find
          subtitles for it. Deluno passes a file over before adding it, so
          MediaMop can tidy it up first and say when it is ready.
        </p>
      </div>

      {connections.isLoading ? (
        <p className="text-sm text-[var(--mm-text2)]">Loading…</p>
      ) : null}

      {connections.data?.length === 0 && !adding ? (
        <p className="text-sm text-[var(--mm-text2)]">
          No apps are connected yet, so nothing is being sent to MediaMop. Add
          one below to get started.
        </p>
      ) : null}

      {connections.data?.map((connection) => (
        <ConnectionCard key={connection.id} connection={connection} />
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
            Add a media manager
          </button>
        </div>
      )}
    </div>
  );
}
