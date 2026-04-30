import { useCallback } from "react";
import { useSuiteSettingsQuery } from "../suite/queries";

function parseIso(iso: string): Date {
  // Backend timestamps have no Z suffix — append it to force UTC parsing.
  const s = iso.endsWith("Z") || iso.includes("+") ? iso : iso + "Z";
  return new Date(s);
}

export function useAppDateFormatter(): (
  iso: string | null | undefined,
) => string {
  const q = useSuiteSettingsQuery();
  const tz = q.data?.app_timezone || undefined;

  return useCallback(
    (iso: string | null | undefined): string => {
      if (!iso) return "—";
      try {
        return new Intl.DateTimeFormat(undefined, {
          dateStyle: "medium",
          timeStyle: "short",
          timeZone: tz,
        }).format(parseIso(iso));
      } catch {
        return iso;
      }
    },
    [tz],
  );
}

export function formatAppDate(
  iso: string | null | undefined,
  tz?: string,
): string {
  if (!iso) return "—";
  try {
    return new Intl.DateTimeFormat(undefined, {
      dateStyle: "medium",
      timeStyle: "short",
      timeZone: tz || undefined,
    }).format(parseIso(iso));
  } catch {
    return iso ?? "—";
  }
}
