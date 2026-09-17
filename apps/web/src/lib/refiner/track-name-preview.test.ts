import { describe, expect, it } from "vitest";
import {
  DEFAULT_TRACK_NAME_TEMPLATE,
  SAMPLE_TRACK,
  previewTrackName,
  trackNameTemplateError,
} from "./track-name-preview";

describe("trackNameTemplateError", () => {
  it("accepts every known placeholder", () => {
    expect(
      trackNameTemplateError("{language}{variant} {channels} {codec} {flags}"),
    ).toBeNull();
  });

  it("accepts a template with no placeholders at all", () => {
    expect(trackNameTemplateError("Audio")).toBeNull();
  });

  it("names the first unknown placeholder", () => {
    const error = trackNameTemplateError("{language} {bogus} {codec}");
    expect(error).toContain("{bogus}");
    expect(error).toContain("{language}");
    expect(error).toContain("{flags}");
  });
});

describe("previewTrackName", () => {
  it("renders the default template against the sample track", () => {
    expect(previewTrackName(DEFAULT_TRACK_NAME_TEMPLATE, SAMPLE_TRACK)).toBe(
      "English (VFQ) 5.1 TrueHD",
    );
  });

  it("renders an empty variant as nothing, not a stray space", () => {
    expect(
      previewTrackName(DEFAULT_TRACK_NAME_TEMPLATE, {
        ...SAMPLE_TRACK,
        variant: null,
      }),
    ).toBe("English 5.1 TrueHD");
  });

  it("renders flags for each override context", () => {
    expect(
      previewTrackName("{language} {flags}", {
        ...SAMPLE_TRACK,
        flags: { forced: true },
      }),
    ).toBe("English Forced");
    expect(
      previewTrackName("{language} {flags}", {
        ...SAMPLE_TRACK,
        flags: { hearingImpaired: true },
      }),
    ).toBe("English Hearing Impaired");
  });

  it("collapses whitespace left by an empty placeholder and trims the ends", () => {
    expect(previewTrackName("  {language}  {flags}  ", SAMPLE_TRACK)).toBe(
      "English",
    );
  });

  it("returns null for a template with an unknown placeholder", () => {
    expect(previewTrackName("{language} {bogus}", SAMPLE_TRACK)).toBeNull();
  });

  it("maps common channel counts", () => {
    expect(
      previewTrackName("{channels}", { ...SAMPLE_TRACK, channels: 2 }),
    ).toBe("2.0");
    expect(
      previewTrackName("{channels}", { ...SAMPLE_TRACK, channels: 8 }),
    ).toBe("7.1");
  });
});
