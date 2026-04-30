import { describe, expect, it } from "vitest";
import { ApiHttpError } from "./client";
import {
  httpStatusFromApiError,
  isHttpErrorFromApi,
  isLikelyNetworkFailure,
  isLikelyViteProxyUpstreamDown,
} from "./error-guards";

describe("error-guards", () => {
  it("treats TypeError as network", () => {
    expect(isLikelyNetworkFailure(new TypeError("Failed to fetch"))).toBe(true);
  });

  it("treats Failed to fetch as network", () => {
    expect(isLikelyNetworkFailure(new Error("Failed to fetch"))).toBe(true);
  });

  it("does not treat HTTP-shaped API errors as network", () => {
    expect(isLikelyNetworkFailure(new Error("bootstrap status: 503"))).toBe(
      false,
    );
    expect(isLikelyNetworkFailure(new Error("me: 503"))).toBe(false);
  });

  it("detects HTTP errors from auth-api throws", () => {
    expect(
      isHttpErrorFromApi(
        new ApiHttpError("/api/v1/auth/me", 401, "Signed out"),
      ),
    ).toBe(true);
    expect(isHttpErrorFromApi(new Error("bootstrap status: 503"))).toBe(true);
    expect(isHttpErrorFromApi(new Error("me: 401"))).toBe(true);
    expect(isHttpErrorFromApi(new Error("CSRF: 403"))).toBe(true);
    expect(isHttpErrorFromApi(new Error("dashboard status: 502"))).toBe(true);
    expect(isHttpErrorFromApi(new Error("activity recent: 403"))).toBe(true);
    expect(isHttpErrorFromApi(new Error("random"))).toBe(false);
  });

  it("parses status from HTTP-shaped errors", () => {
    expect(
      httpStatusFromApiError(
        new ApiHttpError("/api/v1/auth/me", 401, "Signed out"),
      ),
    ).toBe(401);
    expect(httpStatusFromApiError(new Error("bootstrap status: 503"))).toBe(
      503,
    );
    expect(httpStatusFromApiError(new Error("me: 422"))).toBe(422);
    expect(httpStatusFromApiError(new Error("CSRF: 400"))).toBe(400);
    expect(httpStatusFromApiError(new Error("dashboard status: 401"))).toBe(
      401,
    );
    expect(httpStatusFromApiError(new Error("activity recent: 500"))).toBe(500);
    expect(httpStatusFromApiError(new Error("nope"))).toBe(null);
  });

  it("treats bootstrap/me HTTP 500 in Vite dev as proxy upstream down", () => {
    const expectProxyDown = Boolean(import.meta.env.DEV);
    expect(
      isLikelyViteProxyUpstreamDown(new Error("bootstrap status: 500")),
    ).toBe(expectProxyDown);
    expect(isLikelyViteProxyUpstreamDown(new Error("me: 500"))).toBe(
      expectProxyDown,
    );
  });

  it("does not treat non-500 API HTTP errors as Vite proxy upstream down", () => {
    expect(
      isLikelyViteProxyUpstreamDown(new Error("bootstrap status: 503")),
    ).toBe(false);
    expect(isLikelyViteProxyUpstreamDown(new Error("me: 401"))).toBe(false);
  });
});
