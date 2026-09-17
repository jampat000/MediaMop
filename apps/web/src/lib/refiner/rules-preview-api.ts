import { fetchCsrfToken } from "../api/auth-api";
import { apiFetch, readJson, requireOk } from "../api/client";

import { type RefinerRuleSetWrite } from "./libraries-api";

export type RefinerRulesPreviewTrackType = "video" | "audio" | "subtitle";
export type RefinerRulesPreviewAction = "keep" | "drop";

export interface RefinerRulesPreviewTrack {
  index: number;
  type: RefinerRulesPreviewTrackType;
  codec: string;
  language: string;
  title: string;
  channels: number;
  action: RefinerRulesPreviewAction;
  default: boolean;
  forced: boolean;
  reasons: string[];
}

export interface RefinerRulesPreviewOriginalLanguage {
  lookup_status: "matched" | "no_match" | "not_configured" | "unreachable";
  lookup_detail: string;
  original_language: string | null;
  note: string;
}

export interface RefinerRulesPreviewResult {
  library_id: number;
  media_scope: "movie" | "tv";
  inspected_path: string;
  tracks: RefinerRulesPreviewTrack[];
  notes: string[];
  metadata_notes: string[];
  remux_required: boolean;
  estimated_size_reduction_bytes: number | null;
  estimated_size_reduction_is_estimate: boolean;
  original_language: RefinerRulesPreviewOriginalLanguage | null;
}

export type RefinerRulesPreviewRequest = {
  libraryId: number;
  /** Exactly one of these two must be given. */
  relativePath?: string;
  absolutePath?: string;
  /** Unsaved rule edits to try; omit to preview the library's saved rule set. */
  rules?: RefinerRuleSetWrite;
};

/** "Try on a file" (#502): read-only, never queues or writes anything. */
export async function previewRefinerRules({
  libraryId,
  relativePath,
  absolutePath,
  rules,
}: RefinerRulesPreviewRequest): Promise<RefinerRulesPreviewResult> {
  const csrf_token = await fetchCsrfToken();
  const path = `/api/v1/refiner/libraries/${libraryId}/preview`;
  const response = await apiFetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      csrf_token,
      ...(relativePath ? { relative_path: relativePath } : {}),
      ...(absolutePath ? { absolute_path: absolutePath } : {}),
      ...(rules ? { rules } : {}),
    }),
  });
  await requireOk(path, response, "Could not preview these rules on that file");
  return readJson<RefinerRulesPreviewResult>(response);
}
