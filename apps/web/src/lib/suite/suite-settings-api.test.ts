import { describe, expect, it } from "vitest";
import { suiteSecurityOverviewPath, suiteSettingsPath } from "./suite-settings-api";

describe("suite settings API paths", () => {
  it("uses suite settings and security-overview routes", () => {
    expect(suiteSettingsPath()).toBe("/api/v1/suite/settings");
    expect(suiteSecurityOverviewPath()).toBe("/api/v1/suite/security-overview");
  });
});
