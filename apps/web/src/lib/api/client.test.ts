import { afterEach, describe, expect, it, vi } from "vitest";
import { apiErrorDetailToString, apiFetch, resetUnauthorizedHandlingForTests, setUnauthorizedHandler } from "./client";

afterEach(() => {
  resetUnauthorizedHandlingForTests();
  vi.restoreAllMocks();
});

describe("apiErrorDetailToString", () => {
  it("returns strings as-is", () => {
    expect(apiErrorDetailToString("Wrong password")).toBe("Wrong password");
  });

  it("joins FastAPI-style validation array messages with field path", () => {
    expect(
      apiErrorDetailToString([
        { type: "string_too_short", loc: ["body", "new_password"], msg: "Too short", input: "x" },
      ]),
    ).toBe("new_password: Too short");
  });

  it("stringifies plain objects instead of object Object", () => {
    expect(apiErrorDetailToString({ nested: 1 })).toBe(JSON.stringify({ nested: 1 }));
  });

  it("returns empty for nullish", () => {
    expect(apiErrorDetailToString(undefined)).toBe("");
    expect(apiErrorDetailToString(null)).toBe("");
  });
});

describe("apiFetch unauthorized handling", () => {
  it("calls the central unauthorized handler once for repeated 401s", async () => {
    const handler = vi.fn();
    setUnauthorizedHandler(handler);
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(new Response("", { status: 401 })),
    );

    await apiFetch("/api/v1/suite/settings");
    await apiFetch("/api/v1/activity/recent");

    expect(handler).toHaveBeenCalledTimes(1);
    expect(handler).toHaveBeenCalledWith("/api/v1/suite/settings");
  });

  it("resets unauthorized suppression after a non-401 response", async () => {
    const handler = vi.fn();
    setUnauthorizedHandler(handler);
    vi.stubGlobal(
      "fetch",
      vi
        .fn()
        .mockResolvedValueOnce(new Response("", { status: 401 }))
        .mockResolvedValueOnce(new Response("{}", { status: 200 }))
        .mockResolvedValueOnce(new Response("", { status: 401 })),
    );

    await apiFetch("/api/v1/suite/settings");
    await apiFetch("/api/v1/auth/me");
    await apiFetch("/api/v1/activity/recent");

    expect(handler).toHaveBeenCalledTimes(2);
  });
});
