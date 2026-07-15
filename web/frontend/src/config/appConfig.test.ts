import { afterEach, describe, expect, it, vi } from "vitest";
import { __resetAppEnvConfigForTests, getAppEnvConfig } from "./appConfig";

const REQUIRED_ENV = {
  VITE_ENTRA_CLIENT_ID: "client-id",
  VITE_ENTRA_AUTHORITY: "https://login.microsoftonline.com/tenant-id",
  VITE_ENTRA_REDIRECT_URI: "http://localhost:5173",
  VITE_ENTRA_API_SCOPE: "api://api-id/HotelAgent.Access",
};

describe("getAppEnvConfig", () => {
  afterEach(() => {
    __resetAppEnvConfigForTests();
    vi.unstubAllEnvs();
  });

  it("reads and validates every required Vite env var", () => {
    for (const [key, value] of Object.entries(REQUIRED_ENV)) {
      vi.stubEnv(key, value);
    }
    vi.stubEnv("VITE_BACKEND_BASE_URL", "");

    const config = getAppEnvConfig();
    expect(config).toEqual({
      entraClientId: "client-id",
      entraAuthority: "https://login.microsoftonline.com/tenant-id",
      entraRedirectUri: "http://localhost:5173",
      entraApiScope: "api://api-id/HotelAgent.Access",
      backendBaseUrl: "",
    });
  });

  it("memoizes the config after the first successful read", () => {
    for (const [key, value] of Object.entries(REQUIRED_ENV)) {
      vi.stubEnv(key, value);
    }
    const first = getAppEnvConfig();
    vi.stubEnv("VITE_ENTRA_CLIENT_ID", "changed-but-should-not-be-picked-up");
    const second = getAppEnvConfig();
    expect(second).toBe(first);
  });

  it("throws a helpful error when a required variable is missing", () => {
    vi.stubEnv("VITE_ENTRA_CLIENT_ID", "");
    vi.stubEnv("VITE_ENTRA_AUTHORITY", REQUIRED_ENV.VITE_ENTRA_AUTHORITY);
    vi.stubEnv("VITE_ENTRA_REDIRECT_URI", REQUIRED_ENV.VITE_ENTRA_REDIRECT_URI);
    vi.stubEnv("VITE_ENTRA_API_SCOPE", REQUIRED_ENV.VITE_ENTRA_API_SCOPE);

    expect(() => getAppEnvConfig()).toThrow(/VITE_ENTRA_CLIENT_ID/);
  });
});
