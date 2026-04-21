import { describe, expect, it } from "vitest";
import { apiErrorDetailToString } from "./client";

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
