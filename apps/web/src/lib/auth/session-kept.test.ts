import { beforeEach, describe, expect, it } from "vitest";
import {
  clearLoginSucceeded,
  markLoginSucceeded,
  sessionWasNotKept,
} from "./session-kept";

describe("sessionWasNotKept", () => {
  beforeEach(() => {
    clearLoginSucceeded();
  });

  it("is false when no sign-in happened", () => {
    expect(sessionWasNotKept()).toBe(false);
  });

  it("is true when a sign-in succeeded moments ago", () => {
    markLoginSucceeded();
    expect(sessionWasNotKept()).toBe(true);
  });

  it("is consumed, so the explanation shows once", () => {
    markLoginSucceeded();
    expect(sessionWasNotKept()).toBe(true);
    expect(sessionWasNotKept()).toBe(false);
  });

  it("is false once the window has passed, so a normal expiry is not mislabelled", () => {
    markLoginSucceeded();
    expect(sessionWasNotKept(Date.now() + 60_000)).toBe(false);
  });
});
