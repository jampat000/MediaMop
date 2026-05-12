import { useState } from "react";
import type { NotificationChannelOut } from "../../lib/suite/types";
import {
  useCreateNotificationChannelMutation,
  useDeleteNotificationChannelMutation,
  useSuiteNotificationChannelsQuery,
  useTestNotificationChannelMutation,
  useUpdateNotificationChannelMutation,
} from "../../lib/suite/queries";
import { mmActionButtonClass, mmEditableTextFieldClass } from "../../lib/ui/mm-control-roles";
import {
  mmModuleTabBlurbBandClass,
  mmModuleTabBlurbTextClass,
} from "../../lib/ui/mm-module-tab-blurb";
import { SUITE_SETTINGS_DASH_CARD_CLASS } from "./settings-shared";

const EVENT_LABELS: Record<string, string> = {
  job_completed: "Any job completed",
  job_failed: "Any job permanently failed",
  refiner_job_completed: "Refiner job completed",
  refiner_job_failed: "Refiner job permanently failed",
  pruner_job_completed: "Pruner job completed",
  pruner_job_failed: "Pruner job permanently failed",
  subber_job_completed: "Subber job completed",
  subber_job_failed: "Subber job permanently failed",
};

type NotificationFormData = {
  label: string;
  provider: string;
  url: string;
  events: string[];
  enabled: boolean;
};

type ChannelFormProps = {
  initial?: Partial<NotificationFormData>;
  supportedEvents: string[];
  onSave: (data: NotificationFormData) => Promise<void>;
  onCancel: () => void;
  saving: boolean;
  saveError: string | null;
};

function ChannelForm({
  initial,
  supportedEvents,
  onSave,
  onCancel,
  saving,
  saveError,
}: ChannelFormProps) {
  const [label, setLabel] = useState(initial?.label ?? "");
  const [provider, setProvider] = useState<string>(initial?.provider ?? "webhook");
  const [url, setUrl] = useState(initial?.url ?? "");
  const [events, setEvents] = useState<string[]>(initial?.events ?? ["job_failed"]);
  const [enabled, setEnabled] = useState(initial?.enabled ?? true);

  const toggleEvent = (event: string) => {
    setEvents((prev) =>
      prev.includes(event) ? prev.filter((e) => e !== event) : [...prev, event],
    );
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    await onSave({ label, provider, url, events, enabled });
  };

  return (
    <form onSubmit={(e) => void handleSubmit(e)} className="space-y-4">
      <label className="block text-sm text-[var(--mm-text2)]">
        <span className="mb-1 block text-xs font-medium uppercase tracking-wide text-[var(--mm-text3)]">
          Label
        </span>
        <input
          type="text"
          className={mmEditableTextFieldClass}
          value={label}
          onChange={(e) => setLabel(e.target.value)}
          placeholder="e.g. Discord alerts"
          required
          maxLength={255}
          disabled={saving}
        />
      </label>

      <label className="block text-sm text-[var(--mm-text2)]">
        <span className="mb-1 block text-xs font-medium uppercase tracking-wide text-[var(--mm-text3)]">
          Provider
        </span>
        <select
          className={`${mmEditableTextFieldClass} w-full max-w-xs`}
          value={provider}
          onChange={(e) => setProvider(e.target.value)}
          disabled={saving}
        >
          <option value="webhook">Generic webhook (JSON POST)</option>
          <option value="discord">Discord webhook</option>
        </select>
      </label>

      <label className="block text-sm text-[var(--mm-text2)]">
        <span className="mb-1 block text-xs font-medium uppercase tracking-wide text-[var(--mm-text3)]">
          Webhook URL
        </span>
        <input
          type="url"
          className={mmEditableTextFieldClass}
          value={url}
          onChange={(e) => setUrl(e.target.value)}
          placeholder="https://..."
          required
          disabled={saving}
        />
      </label>

      <fieldset>
        <legend className="mb-2 text-xs font-medium uppercase tracking-wide text-[var(--mm-text3)]">
          Trigger events
        </legend>
        <div className="grid grid-cols-1 gap-1.5 sm:grid-cols-2">
          {supportedEvents.map((event) => (
            <label
              key={event}
              className="flex cursor-pointer items-center gap-2 text-sm text-[var(--mm-text2)]"
            >
              <input
                type="checkbox"
                className="h-4 w-4 shrink-0 accent-[var(--mm-accent)]"
                checked={events.includes(event)}
                onChange={() => toggleEvent(event)}
                disabled={saving}
              />
              {EVENT_LABELS[event] ?? event}
            </label>
          ))}
        </div>
      </fieldset>

      <label className="flex cursor-pointer items-center gap-2 text-sm text-[var(--mm-text2)]">
        <input
          type="checkbox"
          className="h-4 w-4 shrink-0 accent-[var(--mm-accent)]"
          checked={enabled}
          onChange={(e) => setEnabled(e.target.checked)}
          disabled={saving}
        />
        Enabled
      </label>

      {saveError ? (
        <p
          className="rounded-md border border-red-500/40 bg-red-950/25 px-3 py-2 text-sm text-red-200"
          role="alert"
        >
          {saveError}
        </p>
      ) : null}

      <div className="flex gap-2">
        <button
          type="submit"
          className={mmActionButtonClass({
            variant: "primary",
            disabled: saving || !label.trim() || !url.trim() || events.length === 0,
          })}
          disabled={saving || !label.trim() || !url.trim() || events.length === 0}
        >
          {saving ? "Saving..." : "Save channel"}
        </button>
        <button
          type="button"
          className={mmActionButtonClass({ variant: "tertiary", disabled: saving })}
          disabled={saving}
          onClick={onCancel}
        >
          Cancel
        </button>
      </div>
    </form>
  );
}

type ChannelRowProps = {
  channel: NotificationChannelOut;
  supportedEvents: string[];
  onEdit: () => void;
  onDelete: () => void;
  onTest: () => void;
  testing: boolean;
  testResult: { ok: boolean; error: string | null } | null;
  deleting: boolean;
};

function ChannelRow({
  channel,
  onEdit,
  onDelete,
  onTest,
  testing,
  testResult,
  deleting,
}: ChannelRowProps) {
  return (
    <div className="rounded-md border border-[var(--mm-border)] bg-[var(--mm-card-bg)] px-4 py-3">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0 space-y-1">
          <div className="flex flex-wrap items-center gap-2">
            <span className="font-medium text-[var(--mm-text1)]">{channel.label}</span>
            <span className="rounded-full border border-[var(--mm-border)] px-2 py-0.5 text-xs text-[var(--mm-text3)]">
              {channel.provider}
            </span>
            {!channel.enabled ? (
              <span className="rounded-full border border-yellow-500/40 bg-yellow-950/20 px-2 py-0.5 text-xs text-yellow-300">
                Disabled
              </span>
            ) : null}
          </div>
          <p className="break-all font-mono text-xs text-[var(--mm-text3)]">{channel.url}</p>
          <p className="text-xs text-[var(--mm-text3)]">
            Events: {channel.events.length > 0 ? channel.events.map((e) => EVENT_LABELS[e] ?? e).join(", ") : "None"}
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            className={mmActionButtonClass({ variant: "tertiary", disabled: testing || deleting })}
            disabled={testing || deleting}
            onClick={onTest}
          >
            {testing ? "Testing..." : "Send test"}
          </button>
          <button
            type="button"
            className={mmActionButtonClass({ variant: "secondary", disabled: deleting })}
            disabled={deleting}
            onClick={onEdit}
          >
            Edit
          </button>
          <button
            type="button"
            className={mmActionButtonClass({ variant: "tertiary", disabled: deleting })}
            disabled={deleting}
            onClick={onDelete}
          >
            {deleting ? "Removing..." : "Remove"}
          </button>
        </div>
      </div>
      {testResult ? (
        <p
          className={`mt-2 rounded-md border px-3 py-2 text-sm ${
            testResult.ok
              ? "border-emerald-500/30 bg-emerald-950/20 text-emerald-200"
              : "border-red-500/40 bg-red-950/25 text-red-200"
          }`}
          role="alert"
        >
          {testResult.ok
            ? "Test notification sent successfully."
            : `Test failed: ${testResult.error ?? "Unknown error"}`}
        </p>
      ) : null}
    </div>
  );
}

export function SettingsNotificationsTab() {
  const channelsQ = useSuiteNotificationChannelsQuery();
  const createMutation = useCreateNotificationChannelMutation();
  const updateMutation = useUpdateNotificationChannelMutation();
  const deleteMutation = useDeleteNotificationChannelMutation();
  const testMutation = useTestNotificationChannelMutation();

  const [showAddForm, setShowAddForm] = useState(false);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [deletingId, setDeletingId] = useState<number | null>(null);
  const [testingId, setTestingId] = useState<number | null>(null);
  const [testResults, setTestResults] = useState<
    Record<number, { ok: boolean; error: string | null }>
  >({});

  const supportedEvents = channelsQ.data?.supported_events ?? Object.keys(EVENT_LABELS);

  const handleCreate = async (data: NotificationFormData) => {
    await createMutation.mutateAsync(data);
    setShowAddForm(false);
  };

  const handleUpdate = async (id: number, data: NotificationFormData) => {
    await updateMutation.mutateAsync({ id, data });
    setEditingId(null);
  };

  const handleDelete = async (id: number) => {
    setDeletingId(id);
    try {
      await deleteMutation.mutateAsync(id);
    } finally {
      setDeletingId(null);
    }
  };

  const handleTest = async (id: number) => {
    setTestingId(id);
    setTestResults((prev) => {
      const next = { ...prev };
      delete next[id];
      return next;
    });
    try {
      const result = await testMutation.mutateAsync(id);
      setTestResults((prev) => ({ ...prev, [id]: result }));
    } catch (err) {
      setTestResults((prev) => ({
        ...prev,
        [id]: { ok: false, error: err instanceof Error ? err.message : "Unknown error" },
      }));
    } finally {
      setTestingId(null);
    }
  };

  return (
    <div data-testid="suite-settings-notifications" className="mm-bubble-stack">
      <div className={mmModuleTabBlurbBandClass}>
        <p className={mmModuleTabBlurbTextClass}>
          Send outbound webhook notifications when jobs complete or permanently fail. Supports
          generic JSON webhooks and Discord.
        </p>
      </div>

      <section className={SUITE_SETTINGS_DASH_CARD_CLASS} aria-labelledby="suite-settings-notifications-heading">
        <div className="mm-card-action-body">
          <div>
            <h3
              id="suite-settings-notifications-heading"
              className="text-base font-semibold text-[var(--mm-text1)]"
            >
              Notification channels
            </h3>
            <p className="mt-1 text-sm text-[var(--mm-text2)]">
              Each channel routes job events to a webhook URL. Use &ldquo;Send test&rdquo; to verify a channel
              before relying on it.
            </p>
          </div>

          {channelsQ.isLoading ? (
            <p className="text-sm text-[var(--mm-text3)]">Loading channels...</p>
          ) : channelsQ.isError ? (
            <p
              className="rounded-md border border-red-500/40 bg-red-950/25 px-3 py-2 text-sm text-red-200"
              role="alert"
            >
              {channelsQ.error instanceof Error
                ? channelsQ.error.message
                : "Could not load notification channels."}
            </p>
          ) : (
            <div className="space-y-3">
              {(channelsQ.data?.items.length ?? 0) === 0 && !showAddForm ? (
                <p className="text-sm text-[var(--mm-text3)]">
                  No notification channels configured yet.
                </p>
              ) : null}
              {channelsQ.data?.items.map((channel) =>
                editingId === channel.id ? (
                  <div
                    key={channel.id}
                    className="rounded-md border border-[var(--mm-border)] bg-[var(--mm-card-bg)] px-4 py-4"
                  >
                    <p className="mb-3 text-xs font-semibold uppercase tracking-wide text-[var(--mm-text3)]">
                      Edit channel
                    </p>
                    <ChannelForm
                      initial={{
                        label: channel.label,
                        provider: channel.provider as "webhook",
                        url: channel.url,
                        events: channel.events,
                        enabled: channel.enabled,
                      }}
                      supportedEvents={supportedEvents}
                      onSave={(data) => handleUpdate(channel.id, data)}
                      onCancel={() => setEditingId(null)}
                      saving={updateMutation.isPending}
                      saveError={
                        updateMutation.isError
                          ? updateMutation.error instanceof Error
                            ? updateMutation.error.message
                            : "Could not save."
                          : null
                      }
                    />
                  </div>
                ) : (
                  <ChannelRow
                    key={channel.id}
                    channel={channel}
                    supportedEvents={supportedEvents}
                    onEdit={() => setEditingId(channel.id)}
                    onDelete={() => void handleDelete(channel.id)}
                    onTest={() => void handleTest(channel.id)}
                    testing={testingId === channel.id}
                    testResult={testResults[channel.id] ?? null}
                    deleting={deletingId === channel.id}
                  />
                ),
              )}
            </div>
          )}

          {showAddForm ? (
            <div className="rounded-md border border-[var(--mm-border)] bg-[var(--mm-card-bg)] px-4 py-4">
              <p className="mb-3 text-xs font-semibold uppercase tracking-wide text-[var(--mm-text3)]">
                New channel
              </p>
              <ChannelForm
                supportedEvents={supportedEvents}
                onSave={handleCreate}
                onCancel={() => setShowAddForm(false)}
                saving={createMutation.isPending}
                saveError={
                  createMutation.isError
                    ? createMutation.error instanceof Error
                      ? createMutation.error.message
                      : "Could not create channel."
                    : null
                }
              />
            </div>
          ) : null}
        </div>

        {!showAddForm && editingId === null ? (
          <div className="mm-card-action-footer">
            <button
              type="button"
              className={mmActionButtonClass({ variant: "secondary" })}
              onClick={() => setShowAddForm(true)}
            >
              Add notification channel
            </button>
          </div>
        ) : null}
      </section>
    </div>
  );
}
