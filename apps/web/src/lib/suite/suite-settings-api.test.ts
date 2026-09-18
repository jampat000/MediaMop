import { afterEach, describe, expect, it, vi } from "vitest";
import {
  deleteNotificationChannel,
  suiteConfigurationBackupsPath,
  suiteConfigurationBundlePath,
  suiteSecurityOverviewPath,
  suiteSettingsPath,
  suiteUpdateStatusPath,
} from "./suite-settings-api";

afterEach(() => {
  vi.restoreAllMocks();
});

describe("suite settings API paths", () => {
  it("uses suite settings and security-overview routes", () => {
    expect(suiteSettingsPath()).toBe("/api/v1/suite/settings");
    expect(suiteSecurityOverviewPath()).toBe("/api/v1/suite/security-overview");
    expect(suiteConfigurationBundlePath()).toBe(
      "/api/v1/suite/configuration-bundle",
    );
    expect(suiteConfigurationBackupsPath()).toBe(
      "/api/v1/suite/configuration-backups",
    );
    // One address per handler since 3.0.0. The `/suite/settings/configuration-bundle` and
    // `/system/suite-configuration-bundle` aliases the Python suite also answered on are gone,
    // and so is the client loop that tried each one until something was not a 404.
    expect(suiteUpdateStatusPath()).toBe("/api/v1/suite/update-status");
  });

  it("sends a CSRF header when deleting a notification channel", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ csrf_token: "csrf-test" }), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        }),
      )
      .mockResolvedValueOnce(new Response(null, { status: 204 }));
    vi.stubGlobal("fetch", fetchMock);

    await deleteNotificationChannel(7);

    expect(fetchMock).toHaveBeenCalledTimes(2);
    const [, request] = fetchMock.mock.calls[1] as [string, RequestInit];
    expect(request.method).toBe("DELETE");
    expect(request.headers).toMatchObject({ "X-CSRF-Token": "csrf-test" });
  });
});
