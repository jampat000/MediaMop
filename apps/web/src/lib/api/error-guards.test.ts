import { describe, expect, it } from "vitest";
import { httpStatusFromApiError, isHttpErrorFromApi, isLikelyNetworkFailure } from "./error-guards";

describe("error-guards", () => {
  it("treats TypeError as network", () => {
    expect(isLikelyNetworkFailure(new TypeError("Failed to fetch"))).toBe(true);
  });

  it("treats Failed to fetch as network", () => {
    expect(isLikelyNetworkFailure(new Error("Failed to fetch"))).toBe(true);
  });

  it("does not treat HTTP-shaped API errors as network", () => {
    expect(isLikelyNetworkFailure(new Error("bootstrap status: 503"))).toBe(false);
    expect(isLikelyNetworkFailure(new Error("me: 503"))).toBe(false);
  });

  it("detects HTTP errors from auth-api throws", () => {
    expect(isHttpErrorFromApi(new Error("bootstrap status: 503"))).toBe(true);
    expect(isHttpErrorFromApi(new Error("me: 401"))).toBe(true);
    expect(isHttpErrorFromApi(new Error("CSRF: 403"))).toBe(true);
    expect(isHttpErrorFromApi(new Error("dashboard status: 502"))).toBe(true);
    expect(isHttpErrorFromApi(new Error("random"))).toBe(false);
  });

  it("parses status from HTTP-shaped errors", () => {
    expect(httpStatusFromApiError(new Error("bootstrap status: 503"))).toBe(503);
    expect(httpStatusFromApiError(new Error("me: 422"))).toBe(422);
    expect(httpStatusFromApiError(new Error("CSRF: 400"))).toBe(400);
    expect(httpStatusFromApiError(new Error("dashboard status: 401"))).toBe(401);
    expect(httpStatusFromApiError(new Error("nope"))).toBe(null);
  });
});
