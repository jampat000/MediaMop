import { describe, expect, it } from "vitest";
import {
  configurationBundlePaths,
  suiteConfigurationBackupsPath,
  suiteConfigurationBundlePath,
  suiteSecurityOverviewPath,
  suiteSettingsPath,
} from "./suite-settings-api";

describe("suite settings API paths", () => {
  it("uses suite settings and security-overview routes", () => {
    expect(suiteSettingsPath()).toBe("/api/v1/suite/settings");
    expect(suiteSecurityOverviewPath()).toBe("/api/v1/suite/security-overview");
    expect(suiteConfigurationBundlePath()).toBe("/api/v1/suite/configuration-bundle");
    expect(suiteConfigurationBackupsPath()).toBe("/api/v1/suite/configuration-backups");
    expect(configurationBundlePaths).toContain("/api/v1/suite/settings/configuration-bundle");
    expect(configurationBundlePaths).toContain("/api/v1/system/suite-configuration-bundle");
  });
});
