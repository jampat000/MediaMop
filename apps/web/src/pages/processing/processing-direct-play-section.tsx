import { useEffect, useState } from "react";

import { PageLoading } from "../../components/shared/page-loading";
import {
  QuietSection,
  quietActionRowClass,
} from "../../components/shared/quiet-section";
import {
  isHttpErrorFromApi,
  isLikelyNetworkFailure,
} from "../../lib/api/error-guards";
import { useMeQuery } from "../../lib/auth/queries";
import type { DirectPlayDevice } from "../../lib/processing/direct-play-api";
import {
  useDirectPlayDevicesQuery,
  useDirectPlayDevicesSaveMutation,
} from "../../lib/processing/direct-play-queries";
import { mmActionButtonClass } from "../../lib/ui/mm-control-roles";

function canEdit(role: string | undefined): boolean {
  return role === "operator" || role === "admin";
}

/** Splits "https://… (checked 2026-09-17)" into its link and its date. */
function parseSource(source: string): {
  url: string | null;
  checked: string | null;
} {
  const url = source.match(/https?:\/\/\S+/)?.[0] ?? null;
  const checked = source.match(/checked\s+(\d{4}-\d{2}-\d{2})/i)?.[1] ?? null;
  return { url, checked };
}

function DeviceSource({
  device,
}: {
  device: DirectPlayDevice;
}): React.ReactElement {
  const { url, checked } = parseSource(device.source);
  if (!url) {
    return <span>Source: {device.source}</span>;
  }
  return (
    <span>
      <a
        className="underline-offset-2 hover:underline"
        href={url}
        target="_blank"
        rel="noopener noreferrer"
        aria-label={`Source for ${device.name}`}
      >
        Source
      </a>
      {checked ? ` · checked ${checked}` : null}
    </span>
  );
}

/**
 * Which devices the operator owns, so each file can say whether it will play on them without
 * the media server converting it (#467). Information only: it changes the badge on files and
 * nothing about how a file is processed.
 */
export function ProcessingDirectPlaySection() {
  const me = useMeQuery();
  const q = useDirectPlayDevicesQuery();
  const save = useDirectPlayDevicesSaveMutation();
  const editable = canEdit(me.data?.role);
  const [selected, setSelected] = useState<Set<string>>(() => new Set());

  useEffect(() => {
    if (!q.data) return;
    setSelected(
      new Set(q.data.devices.filter((d) => d.selected).map((d) => d.id)),
    );
  }, [q.data]);

  if (q.isPending || me.isPending) {
    return <PageLoading label="Loading Direct Play devices" />;
  }
  if (q.isError) {
    return (
      // Something broken, in the language's own shape for it: a sentence with the
      // interrupt marker, not a red box. Raw red-200 on a red-950 wash was also
      // unreadable in the light theme.
      <ul className="mm-interrupt" role="alert">
        <li className="mm-interrupt__item">
          <span className="mm-interrupt__text">
            <strong className="font-semibold">
              Could not load Direct Play devices.
            </strong>{" "}
            {isLikelyNetworkFailure(q.error)
              ? "Check that the Weir API is running."
              : isHttpErrorFromApi(q.error)
                ? "Sign in, then try again."
                : "Request failed."}
          </span>
        </li>
      </ul>
    );
  }
  if (!q.data) return null;

  const devices = q.data.devices;
  const dirty = devices.some((d) => d.selected !== selected.has(d.id));
  const canSave = editable && dirty && !save.isPending;

  const toggle = (id: string) => {
    setSelected((previous) => {
      const next = new Set(previous);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  return (
    <QuietSection
      headingId="processing-direct-play-heading"
      heading="Direct Play devices"
      data-testid="processing-direct-play-section"
    >
      <p className="mm-quiet-note">
        Shows which of your devices can play each file without your media server
        converting it. Information only — Weir never changes a file because of
        this.
      </p>
      {q.data.customised ? (
        <p
          className="mm-quiet-note mt-2"
          data-testid="processing-direct-play-customised"
        >
          This list comes from your own direct-play-devices.json in the Weir
          data folder.
        </p>
      ) : null}
      {!editable ? (
        <p className="mm-quiet-note mt-2">
          Only an operator or admin can change which devices are chosen.
        </p>
      ) : null}
      <div className="mt-6 text-sm leading-relaxed text-[var(--mm-text2)]">
        {devices.length === 0 ? (
          <p className="text-[var(--mm-text3)]">No devices are listed.</p>
        ) : (
          <ul className="grid gap-x-10 lg:grid-cols-2">
            {devices.map((device) => (
              <li
                key={device.id}
                className="flex items-start gap-3 border-b border-[var(--mm-border)] py-3"
              >
                <input
                  id={`direct-play-device-${device.id}`}
                  type="checkbox"
                  className="mt-1"
                  checked={selected.has(device.id)}
                  disabled={!editable || save.isPending}
                  onChange={() => toggle(device.id)}
                />
                <div className="min-w-0">
                  <label
                    htmlFor={`direct-play-device-${device.id}`}
                    className="block font-medium text-[var(--mm-text1)]"
                  >
                    {device.name}
                  </label>
                  <p className="mt-0.5 text-xs leading-5 text-[var(--mm-text3)]">
                    {device.note}
                  </p>
                  <p className="mt-0.5 text-xs leading-5 text-[var(--mm-text3)] [overflow-wrap:anywhere]">
                    <DeviceSource device={device} />
                  </p>
                </div>
              </li>
            ))}
          </ul>
        )}
        {save.isError ? (
          <p className="mm-status-text--failed mt-3 text-sm" role="alert">
            {save.error instanceof Error ? save.error.message : "Save failed."}
          </p>
        ) : null}
      </div>
      <div className={`${quietActionRowClass} mt-8`}>
        <button
          type="button"
          className={mmActionButtonClass({
            variant: "primary",
            disabled: !canSave,
          })}
          disabled={!canSave}
          onClick={() =>
            save.mutate(
              devices.filter((d) => selected.has(d.id)).map((d) => d.id),
            )
          }
        >
          {save.isPending ? "Saving…" : "Save devices"}
        </button>
      </div>
    </QuietSection>
  );
}
