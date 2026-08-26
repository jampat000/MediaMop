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
  radarr: "Sends its Download event when a film has been imported.",
  sonarr: "Sends its Download event when an episode has been imported.",
  deluno:
    "Hands a finished download to Refiner before importing, and waits to be told the cleaned file is ready.",
  native: "Anything else that can post JSON. Use MediaMop's own payload shape.",
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
          <span className="text-[var(--mm-text2)]">What is it?</span>
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
          <span className="text-[var(--mm-text2)]">Address</span>
          <input
            data-testid="media-manager-base-url"
            className={mmEditableTextFieldClass}
            value={form.base_url}
            placeholder="http://10.1.1.142:5099"
            onChange={(e) => setForm({ ...form, base_url: e.target.value })}
          />
          <span className="text-xs text-[var(--mm-text2)]">
            Where MediaMop reaches it, and where it reports finished work back
            to.
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
            Stored encrypted. MediaMop never shows it again.
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
            {connection.base_url || "no address saved"}
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
          Point it at this address:
        </p>
        <code className="mt-1 block break-all text-xs text-[var(--mm-text2)]">
          {connection.webhook_url_path}
        </code>
        {connection.webhook_secret_is_set ? (
          <p className="mt-2 text-xs text-[var(--mm-text2)]">
            A secret is set. It must send it as <code>X-Webhook-Secret</code>.
          </p>
        ) : (
          <p className="mt-2 text-xs text-[var(--mm-text2)]">
            No secret set — anything that can reach MediaMop can post as this
            manager.
          </p>
        )}
        {revealed ? (
          <p
            className="mt-2 break-all rounded bg-[var(--mm-card-bg)] p-2 text-xs text-[var(--mm-text)]"
            data-testid="media-manager-secret"
          >
            {revealed}
            <span className="mt-1 block text-[var(--mm-text2)]">
              Copy it now — this is the only time it is shown.
            </span>
          </p>
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
            ? "Replace secret"
            : "Generate secret"}
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
          A media manager tells MediaMop about files. Radarr and Sonarr say a
          file has been imported, so Subber goes looking for subtitles. Deluno
          hands a file over before importing it, so Refiner cleans it and
          reports back when it is ready.
        </p>
      </div>

      {connections.isLoading ? (
        <p className="text-sm text-[var(--mm-text2)]">Loading…</p>
      ) : null}

      {connections.data?.length === 0 && !adding ? (
        <p className="text-sm text-[var(--mm-text2)]">
          No media managers yet. Nothing will be sent to MediaMop until one is
          added.
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
