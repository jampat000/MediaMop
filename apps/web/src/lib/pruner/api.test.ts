import { describe, expect, it } from "vitest";
import {
  PRUNER_REMOVE_UNWATCHED_STALE_MOVIE_ENTRIES_LABEL,
  PRUNER_REMOVE_WATCHED_LOW_RATING_MOVIE_ENTRIES_LABEL,
  RULE_FAMILY_GENRE_MATCH_REPORTED,
  RULE_FAMILY_PEOPLE_MATCH_REPORTED,
  RULE_FAMILY_STUDIO_MATCH_REPORTED,
  RULE_FAMILY_UNWATCHED_MOVIE_STALE_REPORTED,
  RULE_FAMILY_WATCHED_MOVIE_LOW_RATING_REPORTED,
  RULE_FAMILY_YEAR_RANGE_MATCH_REPORTED,
  prunerApplyEligibilityPath,
  prunerApplyLabelForRuleFamily,
  prunerPreviewRunsListPath,
} from "./api";

describe("prunerApplyEligibilityPath", () => {
  it("scopes apply eligibility under instance + media_scope + preview id", () => {
    expect(
      prunerApplyEligibilityPath(
        5,
        "movies",
        "aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee",
      ),
    ).toBe(
      "/api/v1/pruner/instances/5/scopes/movies/preview-runs/aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee/apply-eligibility",
    );
  });
});

describe("prunerApplyLabelForRuleFamily", () => {
  it("maps new movie rule families to operator-facing apply labels", () => {
    expect(
      prunerApplyLabelForRuleFamily(
        RULE_FAMILY_WATCHED_MOVIE_LOW_RATING_REPORTED,
      ),
    ).toBe(PRUNER_REMOVE_WATCHED_LOW_RATING_MOVIE_ENTRIES_LABEL);
    expect(
      prunerApplyLabelForRuleFamily(RULE_FAMILY_UNWATCHED_MOVIE_STALE_REPORTED),
    ).toBe(PRUNER_REMOVE_UNWATCHED_STALE_MOVIE_ENTRIES_LABEL);
    expect(
      prunerApplyLabelForRuleFamily(RULE_FAMILY_GENRE_MATCH_REPORTED),
    ).toBe("Remove items matching selected genres");
    expect(
      prunerApplyLabelForRuleFamily(RULE_FAMILY_STUDIO_MATCH_REPORTED),
    ).toBe("Remove items from selected studios");
    expect(
      prunerApplyLabelForRuleFamily(RULE_FAMILY_PEOPLE_MATCH_REPORTED),
    ).toBe("Remove items involving selected people");
    expect(
      prunerApplyLabelForRuleFamily(RULE_FAMILY_YEAR_RANGE_MATCH_REPORTED),
    ).toBe("Remove items from selected year range");
  });
});

describe("prunerPreviewRunsListPath", () => {
  it("builds the list URL and optional query string", () => {
    expect(prunerPreviewRunsListPath(12)).toBe(
      "/api/v1/pruner/instances/12/preview-runs",
    );
    const q = prunerPreviewRunsListPath(3, { media_scope: "tv", limit: 7 });
    expect(q).toContain("/api/v1/pruner/instances/3/preview-runs?");
    expect(q).toContain("media_scope=tv");
    expect(q).toContain("limit=7");
  });
});
