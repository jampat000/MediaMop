import { useEffect, useState } from "react";

import {
  fetchServerDirectories,
  type DirectoryBrowseResponse,
} from "../../lib/system/directory-browser-api";
import { mmActionButtonClass } from "../../lib/ui/mm-control-roles";

type Props = {
  title: string;
  value: string;
  disabled?: boolean;
  onSelect: (path: string) => void;
};

export function ServerFolderPickerButton({
  title,
  value,
  disabled,
  onSelect,
}: Props) {
  const [open, setOpen] = useState(false);
  const [path, setPath] = useState<string | null>(null);
  const [data, setData] = useState<DirectoryBrowseResponse | null>(null);
  const [manualPath, setManualPath] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  useEffect(() => {
    if (!open) {
      return;
    }
    setPath(value.trim() || null);
  }, [open, value]);

  useEffect(() => {
    if (!open) {
      return;
    }
    let cancelled = false;
    async function load() {
      setLoading(true);
      setError(null);
      try {
        const response = await fetchServerDirectories(path);
        if (!cancelled) {
          setData(response);
          setNotice(null);
        }
      } catch (err) {
        if (path) {
          try {
            const roots = await fetchServerDirectories(null);
            if (!cancelled) {
              setData(roots);
              setError(null);
              setNotice(
                `"${path}" could not be opened. Showing available drives instead.`,
              );
            }
            return;
          } catch {
            /* fall through */
          }
        }
        if (!cancelled) {
          setData(null);
          setError(
            err instanceof Error ? err.message : "Folder browser unavailable.",
          );
          setNotice(null);
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    }
    void load();
    return () => {
      cancelled = true;
    };
  }, [open, path]);

  function choose(selected: string) {
    onSelect(selected);
    setOpen(false);
  }

  return (
    <>
      <button
        type="button"
        className={mmActionButtonClass({ variant: "tertiary", disabled })}
        disabled={disabled}
        onClick={() => setOpen(true)}
      >
        Browse
      </button>
      {open ? (
        <div
          className="fixed inset-0 z-[9999] flex items-stretch justify-end bg-black/55 p-3 sm:p-6"
          role="dialog"
          aria-modal="true"
        >
          <div className="flex w-full max-w-2xl flex-col overflow-hidden rounded-xl border border-[var(--mm-border)] bg-[var(--mm-card-bg)] shadow-2xl">
            <div className="border-b border-[var(--mm-border)] p-5">
              <div className="flex items-start justify-between gap-4">
                <div>
                  <p className="text-[0.7rem] font-semibold uppercase tracking-[0.16em] text-[var(--mm-text3)]">
                    Filesystem
                  </p>
                  <h2 className="mt-1 text-lg font-semibold text-[var(--mm-text1)]">
                    {title}
                  </h2>
                  <p className="mt-1 text-sm text-[var(--mm-text3)]">
                    Pick a folder visible to the machine running MediaMop, or
                    jump to a UNC/Docker path directly.
                  </p>
                </div>
                <button
                  type="button"
                  className={mmActionButtonClass({ variant: "secondary" })}
                  onClick={() => setOpen(false)}
                >
                  Close
                </button>
              </div>
            </div>
            <div className="border-b border-[var(--mm-border)] p-4">
              <form
                className="mb-3 flex flex-col gap-2 sm:flex-row"
                onSubmit={(event) => {
                  event.preventDefault();
                  const next = manualPath.trim();
                  if (next) {
                    setPath(next);
                  }
                }}
              >
                <input
                  className="mm-input w-full"
                  value={manualPath}
                  onChange={(event) => setManualPath(event.target.value)}
                  placeholder={
                    navigator.platform.toLowerCase().includes("win")
                      ? String.raw`\\nas\media or X:\Media`
                      : "/media/tv"
                  }
                  aria-label="Folder path"
                />
                <button
                  type="submit"
                  className={mmActionButtonClass({
                    variant: "secondary",
                    disabled: loading,
                  })}
                  disabled={loading}
                >
                  Go to path
                </button>
              </form>
              <div className="flex flex-wrap items-center gap-2">
                <button
                  type="button"
                  className={mmActionButtonClass({
                    variant: "secondary",
                    disabled: loading || !data?.parent_path,
                  })}
                  disabled={loading || !data?.parent_path}
                  onClick={() => setPath(data?.parent_path ?? null)}
                >
                  Up
                </button>
                <button
                  type="button"
                  className={mmActionButtonClass({
                    variant: "tertiary",
                    disabled: loading || data?.current_path === null,
                  })}
                  disabled={loading || data?.current_path === null}
                  onClick={() => setPath(null)}
                >
                  Drives
                </button>
                {data?.current_path ? (
                  <button
                    type="button"
                    className={mmActionButtonClass({ variant: "primary" })}
                    onClick={() => choose(data.current_path!)}
                  >
                    Use this folder
                  </button>
                ) : null}
                <div className="min-w-0 flex-1 rounded-md border border-[var(--mm-border)] bg-black/15 px-3 py-2 text-sm text-[var(--mm-text3)]">
                  <span className="block truncate">
                    {data?.current_path ?? "Available drives"}
                  </span>
                </div>
              </div>
              <p className="mt-2 text-xs leading-relaxed text-[var(--mm-text3)]">
                Windows supports local drives, mapped drives, and UNC shares
                such as <span className="font-mono">\\nas\media</span>. Docker
                installs must use container-visible paths such as{" "}
                <span className="font-mono">/media/tv</span>.
              </p>
              {notice ? (
                <p className="mt-3 rounded-md border border-amber-400/25 bg-amber-400/10 px-3 py-2 text-sm text-amber-200">
                  {notice}
                </p>
              ) : null}
            </div>
            <div className="min-h-0 flex-1 overflow-auto p-4">
              {loading ? (
                <div className="rounded-lg border border-dashed border-[var(--mm-border)] p-6 text-sm text-[var(--mm-text3)]">
                  Loading folders...
                </div>
              ) : error ? (
                <div className="rounded-lg border border-red-500/30 bg-red-500/10 p-4 text-sm text-red-200">
                  {error}
                </div>
              ) : data && data.entries.length > 0 ? (
                <div className="space-y-2">
                  {data.entries.map((entry) => (
                    <div
                      key={entry.path}
                      className="flex items-center justify-between gap-3 rounded-lg border border-[var(--mm-border)] bg-black/10 p-3"
                    >
                      <button
                        type="button"
                        className="min-w-0 flex-1 text-left"
                        onClick={() => setPath(entry.path)}
                      >
                        <span className="block truncate text-sm font-semibold text-[var(--mm-text1)]">
                          {entry.name}
                        </span>
                        <span className="block truncate text-xs text-[var(--mm-text3)]">
                          {entry.description ?? entry.path}
                        </span>
                      </button>
                      <button
                        type="button"
                        className={mmActionButtonClass({ variant: "tertiary" })}
                        onClick={() => setPath(entry.path)}
                      >
                        Open
                      </button>
                      <button
                        type="button"
                        className={mmActionButtonClass({
                          variant: "secondary",
                        })}
                        onClick={() => choose(entry.path)}
                      >
                        Select
                      </button>
                    </div>
                  ))}
                </div>
              ) : (
                <div className="rounded-lg border border-dashed border-[var(--mm-border)] p-6 text-sm text-[var(--mm-text3)]">
                  No folders found here.
                </div>
              )}
            </div>
          </div>
        </div>
      ) : null}
    </>
  );
}
