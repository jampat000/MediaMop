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

  expect(await screen.findByText("Audio order")).toBeInTheDocument();
  expect(screen.getByText("Subtitle order")).toBeInTheDocument();
  expect(screen.getByText("Original language")).toBeInTheDocument();
  expect(screen.getByText("Metadata cleanup")).toBeInTheDocument();
  expect(screen.getByText("Metadata provider")).toBeInTheDocument();
  expect(screen.getByDisplayValue(">=5.1")).toBeInTheDocument();

  fireEvent.click(
    screen.getByRole("checkbox", { name: /Keep the original language/ }),
  );
  fireEvent.click(
    screen.getByRole("checkbox", { name: /Remove embedded images/ }),
  );
  fireEvent.click(screen.getByRole("button", { name: "Save rule set" }));

  await waitFor(() => {
    expect(update).toHaveBeenCalledWith(
      4,
      expect.objectContaining({
        keep_original_language: true,
        remove_images: true,
        audio_sorters_json: expect.stringContaining("channels"),
      }),
    );
  });
  const sentRuleSet = update.mock.calls[0]?.[1];
  expect(sentRuleSet).not.toHaveProperty("id");
  expect(sentRuleSet).not.toHaveProperty("used_by_library_count");
  expect(sentRuleSet).not.toHaveProperty("updated_at");

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
