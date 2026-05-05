import type { UserPublic } from "../api/types";

/**
 * Entry routing: where to send the user on initial load (shell root `/`, setup, or login).
 * Authenticated JSON such as `GET /api/v1/dashboard/status` is separate from this helper.
 */

export type EntryDecision =
  | { kind: "wait" }
  | { kind: "redirect"; to: "/" | "/setup" | "/login" };

/**
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
    return { kind: "redirect", to: "/" };
  }
  if (args.bootstrapAllowed === true) {
    return { kind: "redirect", to: "/setup" };
  }
  return { kind: "redirect", to: "/login" };
}
