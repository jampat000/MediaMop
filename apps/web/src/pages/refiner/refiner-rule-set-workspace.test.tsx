import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, expect, it, vi } from "vitest";

import * as authQueries from "../../lib/auth/queries";
import * as librariesApi from "../../lib/refiner/libraries-api";
import type { RefinerRuleSet } from "../../lib/refiner/libraries-api";
import * as providerApi from "../../lib/refiner/metadata-provider-api";
import { RefinerRuleSetWorkspace } from "./refiner-rule-set-workspace";

const ruleSet: RefinerRuleSet = {
  id: 4,
  name: "Feature films",
  primary_audio_lang: "eng",
  secondary_audio_lang: "jpn",
  tertiary_audio_lang: "",
  default_audio_slot: "primary",
  remove_commentary: true,
  subtitle_mode: "keep_listed",
  subtitle_langs_csv: "eng",
  preserve_forced_subs: true,
  preserve_default_subs: true,
  audio_preference_mode: "preferred_langs_quality",
  audio_sorters_json: JSON.stringify([
    { field: "language", value: "eng", reversed: false },
    { field: "channels", value: ">=5.1", reversed: false },
  ]),
  subtitle_sorters_json: JSON.stringify([
    { field: "forced", value: null, reversed: false },
  ]),
  keep_original_language: false,
  original_language_additional_csv: "",
  original_language_keep_only_first: true,
  original_language_first_if_none: true,
  original_language_treat_empty_as_original: false,
  remove_images: false,
  remove_attachments: false,
  remove_title: false,
  remove_language_tags: false,
  remove_other_metadata: false,
  remove_hearing_impaired_subs: false,
  audio_keep_mode: "single",
  subtitle_max_per_language: 0,
  subtitle_quality_strategy: "text_first",
  standardize_track_names: false,
  track_name_template: "{language}{variant} {channels} {codec}",
  track_name_overrides: {
    forced: "{language} {flags}",
    hearing_impaired: "{language} {flags}",
    commentary: "{language} {flags}",
    audio_description: "{language} {flags}",
  },
  clear_video_track_names: false,
  remove_chapters: false,
  used_by_library_count: 2,
  updated_at: "2026-09-01T04:00:00Z",
};

function wrapper({ children }: { children: ReactNode }) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

afterEach(() => {
  vi.restoreAllMocks();
});

it("edits ordered rules, original-language behavior, metadata cleanup, and the provider", async () => {
  vi.spyOn(authQueries, "useMeQuery").mockReturnValue({
    data: { role: "operator" },
  } as ReturnType<typeof authQueries.useMeQuery>);
  vi.spyOn(librariesApi, "fetchRefinerRuleSets").mockResolvedValue([ruleSet]);
  const update = vi
    .spyOn(librariesApi, "updateRefinerRuleSet")
    .mockResolvedValue({
      ...ruleSet,
      keep_original_language: true,
      remove_images: true,
    });
  vi.spyOn(providerApi, "fetchRefinerMetadataProvider").mockResolvedValue({
    provider: "",
    base_url: "https://api.themoviedb.org/3",
    key_configured: false,
    known_providers: ["tmdb"],
  });
  const saveProvider = vi
    .spyOn(providerApi, "putRefinerMetadataProvider")
    .mockResolvedValue({
      provider: "tmdb",
      base_url: "https://api.themoviedb.org/3",
      key_configured: true,
      known_providers: ["tmdb"],
    });
  const testProvider = vi
    .spyOn(providerApi, "testRefinerMetadataProvider")
    .mockResolvedValue({
      status: "matched",
      detail: "TMDb answered successfully.",
    });

  render(<RefinerRuleSetWorkspace />, { wrapper });

  expect(
    await screen.findByRole("heading", { name: "Audio" }),
  ).toBeInTheDocument();
  expect(
    screen.getByRole("heading", { name: "Subtitles" }),
  ).toBeInTheDocument();
  expect(screen.getByText("Original language")).toBeInTheDocument();
  expect(screen.getByText("Remove from container")).toBeInTheDocument();
  expect(screen.getByText("Metadata provider")).toBeInTheDocument();

  const orderedSections = [
    "Audio",
    "Subtitles",
    "Original language",
    "Remove from container",
  ].map((name) => screen.getByRole("heading", { name }));
  orderedSections.slice(0, -1).forEach((heading, index) => {
    expect(heading.compareDocumentPosition(orderedSections[index + 1]!)).toBe(
      Node.DOCUMENT_POSITION_FOLLOWING,
    );
  });

  fireEvent.click(
    screen.getByRole("button", { name: /Advanced track ordering/ }),
  );
  expect(screen.getByText("Audio order")).toBeInTheDocument();
  expect(screen.getByText("Subtitle order")).toBeInTheDocument();
  expect(screen.getByDisplayValue(">=5.1")).toBeInTheDocument();

  fireEvent.click(
    screen.getByRole("checkbox", { name: /Keep the original language/ }),
  );
  fireEvent.click(screen.getByRole("checkbox", { name: /Embedded images/ }));

  // Issue #495/#497: audio keep mode, SDH removal and the subtitle cap/strategy.
  expect(
    screen.getByRole("heading", { name: "Track naming & chapters" }),
  ).toBeInTheDocument();
  fireEvent.change(
    screen.getByRole("combobox", { name: /Audio tracks kept/ }),
    { target: { value: "per_language" } },
  );
  fireEvent.click(
    screen.getByRole("checkbox", { name: /Remove hearing-impaired subtitles/ }),
  );
  fireEvent.change(
    screen.getByRole("spinbutton", {
      name: /Limit subtitles kept per language/,
    }),
    { target: { value: "2" } },
  );
  fireEvent.change(
    screen.getByRole("combobox", { name: /How to pick the best subtitle/ }),
    { target: { value: "accessibility" } },
  );

  // Issue #498: standardize track names, template live preview, and chapters.
  fireEvent.click(
    screen.getByRole("checkbox", {
      name: /Standardize audio and subtitle track names/,
    }),
  );
  expect(
    screen.getByText(
      (_, element) =>
        element?.tagName.toLowerCase() === "span" &&
        element.textContent?.replace(/\s+/g, " ").trim() ===
          "Preview: English (VFQ) 5.1 TrueHD",
    ),
  ).toBeInTheDocument();
  const templateField = screen.getByRole("textbox", {
    name: /Track name template/,
  });
  fireEvent.change(templateField, {
    target: { value: "{language} {bogus}" },
  });
  expect(
    screen.getByText(/Unknown placeholder '\{bogus\}'/),
  ).toBeInTheDocument();
  fireEvent.change(templateField, {
    target: { value: "{language} {codec}" },
  });
  fireEvent.click(
    screen.getByRole("checkbox", { name: /Clear video track names/ }),
  );
  fireEvent.click(screen.getByRole("checkbox", { name: /Remove chapters/ }));

  fireEvent.click(screen.getByRole("button", { name: "Save profile" }));

  await waitFor(() => {
    expect(update).toHaveBeenCalledWith(
      4,
      expect.objectContaining({
        keep_original_language: true,
        remove_images: true,
        audio_sorters_json: expect.stringContaining("channels"),
        audio_keep_mode: "per_language",
        remove_hearing_impaired_subs: true,
        subtitle_max_per_language: 2,
        subtitle_quality_strategy: "accessibility",
        standardize_track_names: true,
        track_name_template: "{language} {codec}",
        clear_video_track_names: true,
        remove_chapters: true,
      }),
    );
  });
  const sentRuleSet = update.mock.calls[0]?.[1];
  expect(sentRuleSet).not.toHaveProperty("id");
  expect(sentRuleSet).not.toHaveProperty("used_by_library_count");
  expect(sentRuleSet).not.toHaveProperty("updated_at");

  fireEvent.click(screen.getByRole("button", { name: "Configure" }));
  fireEvent.change(screen.getByRole("combobox", { name: "Provider" }), {
    target: { value: "tmdb" },
  });
  fireEvent.change(screen.getByLabelText("API key"), {
    target: { value: "secret" },
  });
  fireEvent.click(screen.getByRole("button", { name: "Save and test" }));

  await waitFor(() => {
    expect(saveProvider).toHaveBeenCalledWith(
      expect.objectContaining({ provider: "tmdb", api_key: "secret" }),
    );
    expect(testProvider).toHaveBeenCalled();
    expect(screen.getByText("TMDb answered successfully.")).toBeInTheDocument();
  });
});
