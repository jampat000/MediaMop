import type { UserPublic } from "../api/types";

export type EntryDecision =
  | { kind: "wait" }
  | { kind: "redirect"; to: "/app" | "/setup" | "/login" };

/**
 * Where to send the user on initial load: dashboard, first-run setup, or login.
 * Pure helper — tested without React.
 */
export function resolveEntryDecision(args: {
  meLoading: boolean;
  bootstrapLoading: boolean;
  user: UserPublic | null | undefined;
  bootstrapAllowed: boolean | undefined;
}): EntryDecision {
  if (args.meLoading || args.bootstrapLoading) {
    return { kind: "wait" };
  }
  if (args.user) {
    return { kind: "redirect", to: "/app" };
  }
  if (args.bootstrapAllowed === true) {
    return { kind: "redirect", to: "/setup" };
  }
  return { kind: "redirect", to: "/login" };
}
