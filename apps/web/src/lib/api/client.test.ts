import { afterEach, describe, expect, it, vi } from "vitest";
import {
  ApiHttpError,
  apiErrorDetailToString,
  apiFetch,
  apiResponseErrorMessage,
  resetUnauthorizedHandlingForTests,
  setUnauthorizedHandler,
  throwApiResponseError,
} from "./client";

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
        {
          type: "string_too_short",
          loc: ["body", "new_password"],
          msg: "Too short",
          input: "x",
        },
      ]),
    ).toBe("new_password: Too short");
  });

  it("stringifies plain objects instead of object Object", () => {
    expect(apiErrorDetailToString({ nested: 1 })).toBe(
      JSON.stringify({ nested: 1 }),
    );
  });

  it("returns empty for nullish", () => {
    expect(apiErrorDetailToString(undefined)).toBe("");
    expect(apiErrorDetailToString(null)).toBe("");
  });
});

describe("apiResponseErrorMessage", () => {
  it("normalizes FastAPI string detail", async () => {
    const response = new Response(
      JSON.stringify({ detail: "Wrong password" }),
      {
        status: 401,
        headers: { "Content-Type": "application/json" },
      },
    );

    await expect(
      throwApiResponseError(
        "/api/v1/auth/login",
        response,
        "Could not sign in",
      ),
    ).rejects.toMatchObject({
      name: "ApiHttpError",
      path: "/api/v1/auth/login",
      status: 401,
      message: "Wrong password",
    });
  });

  it("normalizes validation arrays without object Object", async () => {
    const response = new Response(
      JSON.stringify({
        detail: [
          {
            loc: ["body", "password"],
            msg: "String should have at least 8 characters",
          },
        ],
      }),
      { status: 422, headers: { "Content-Type": "application/json" } },
    );

    const normalized = await apiResponseErrorMessage(
      response,
      "Could not save",
    );

    expect(normalized.message).toBe(
      "password: String should have at least 8 characters",
    );
    expect(normalized.message).not.toContain("[object Object]");
  });

  it("normalizes object bodies without object Object", async () => {
    const response = new Response(JSON.stringify({ reason: "missing-route" }), {
      status: 404,
      headers: { "Content-Type": "application/json" },
    });

    const normalized = await apiResponseErrorMessage(
      response,
      "Could not load",
    );

    expect(normalized.message).toBe(
      JSON.stringify({ reason: "missing-route" }),
    );
    expect(normalized.message).not.toContain("[object Object]");
  });

  it("turns HTML responses into operator-safe proxy guidance", async () => {
    const response = new Response("<!doctype html><title>Not found</title>", {
      status: 404,
    });

    const normalized = await apiResponseErrorMessage(
      response,
      "Could not check for updates",
    );

    expect(normalized.message).toContain("received HTML instead of JSON");
  });

  it("exposes status and path on ApiHttpError", () => {
    const error = new ApiHttpError(
      "/api/v1/example",
      503,
      "Service unavailable",
    );

    expect(error.status).toBe(503);
    expect(error.path).toBe("/api/v1/example");
  });
});

describe("apiFetch timeouts", () => {
  it("turns request timeouts into typed ApiHttpError", async () => {
    const timeoutSignal = {
      aborted: true,
      reason: new DOMException("The operation timed out.", "TimeoutError"),
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      dispatchEvent: vi.fn(),
      onabort: null,
      throwIfAborted: vi.fn(),
    } as unknown as AbortSignal;
    vi.spyOn(AbortSignal, "timeout").mockReturnValue(timeoutSignal);
    vi.stubGlobal(
      "fetch",
      vi
        .fn()
        .mockRejectedValue(
          new DOMException("The operation was aborted.", "AbortError"),
        ),
    );

    await expect(apiFetch("/api/v1/suite/settings")).rejects.toMatchObject({
      name: "ApiHttpError",
      status: 0,
      path: "/api/v1/suite/settings",
      timedOut: true,
      message: "Request timed out - the backend may be slow or unreachable.",
    });
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
