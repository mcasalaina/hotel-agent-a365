import { afterEach, describe, expect, it, vi } from "vitest";
import { __resetAppEnvConfigForTests } from "../config/appConfig";
import { buildMsalConfig } from "./msalConfig";

const REQUIRED_ENV = {
  VITE_ENTRA_CLIENT_ID: "client-id",
  VITE_ENTRA_AUTHORITY: "https://login.microsoftonline.com/tenant-id",
  VITE_ENTRA_REDIRECT_URI: "auto",
  VITE_ENTRA_API_SCOPE: "api://api-id/HotelAgent.Access",
};

describe("buildMsalConfig", () => {
  afterEach(() => {
    __resetAppEnvConfigForTests();
    vi.unstubAllEnvs();
  });

  it("uses the MSAL v5 redirect bridge while keeping durable tokens in memory", () => {
    for (const [key, value] of Object.entries(REQUIRED_ENV)) {
      vi.stubEnv(key, value);
    }

    const config = buildMsalConfig();

    expect(config.auth.redirectUri).toBe(`${window.location.origin}/redirect.html`);
    expect(config.cache?.cacheLocation).toBe("memoryStorage");
  });
});
