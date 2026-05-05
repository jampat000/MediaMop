import { describe, expect, it } from "vitest";
import { resolveEntryDecision } from "./routes";

describe("resolveEntryDecision", () => {
  it("waits while queries load", () => {
    expect(
      resolveEntryDecision({
        meLoading: true,
        bootstrapLoading: false,
        user: undefined,
        bootstrapAllowed: undefined,
      }),
    ).toEqual({ kind: "wait" });
    expect(
      resolveEntryDecision({
        meLoading: false,
        bootstrapLoading: true,
        user: null,
        bootstrapAllowed: false,
      }),
    ).toEqual({ kind: "wait" });
  });

  it("sends authenticated users to the app shell", () => {
    expect(
      resolveEntryDecision({
        meLoading: false,
        bootstrapLoading: false,
        user: { id: 1, username: "a", role: "admin" },
        bootstrapAllowed: true,
      }),
    ).toEqual({ kind: "redirect", to: "/" });
  });

  it("sends guests to setup when bootstrap is open", () => {
    expect(
      resolveEntryDecision({
        meLoading: false,
        bootstrapLoading: false,
        user: null,
        bootstrapAllowed: true,
      }),
    ).toEqual({ kind: "redirect", to: "/setup" });
  });

  it("sends guests to login when bootstrap is closed", () => {
    expect(
      resolveEntryDecision({
        meLoading: false,
        bootstrapLoading: false,
        user: null,
        bootstrapAllowed: false,
      }),
    ).toEqual({ kind: "redirect", to: "/login" });
  });
});
