import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { __resetAppEnvConfigForTests } from "../config/appConfig";
import { buildCallSocketUrl, createCallSession, fetchBackendConfig } from "./backendClient";

const REQUIRED_ENV = {
  VITE_ENTRA_CLIENT_ID: "client-id",
  VITE_ENTRA_AUTHORITY: "https://login.microsoftonline.com/tenant-id",
  VITE_ENTRA_REDIRECT_URI: "http://localhost:5173",
  VITE_ENTRA_API_SCOPE: "api://api-id/HotelAgent.Access",
};

function stubRequiredEnv(backendBaseUrl = "") {
  for (const [key, value] of Object.entries(REQUIRED_ENV)) {
    vi.stubEnv(key, value);
  }
  vi.stubEnv("VITE_BACKEND_BASE_URL", backendBaseUrl);
}

describe("backendClient", () => {
  beforeEach(() => {
    __resetAppEnvConfigForTests();
  });

  afterEach(() => {
    vi.unstubAllEnvs();
    vi.unstubAllGlobals();
    __resetAppEnvConfigForTests();
  });

  it("fetchBackendConfig issues an unauthenticated GET to /api/config", async () => {
    stubRequiredEnv();
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ hotelBrandName: "Lyrenza Hotels" }),
    });
    vi.stubGlobal("fetch", fetchMock);

    await fetchBackendConfig();

    expect(fetchMock).toHaveBeenCalledWith(
      "/api/config",
      expect.objectContaining({ method: "GET" }),
    );
    const [, options] = fetchMock.mock.calls[0];
    expect(options.headers).not.toHaveProperty("Authorization");
  });

  it("createCallSession attaches the bearer token only as a header, never in the URL or body", async () => {
    stubRequiredEnv();
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ sessionHandle: "handle-1", expiresAt: "2030-01-01T00:00:00Z" }),
    });
    vi.stubGlobal("fetch", fetchMock);

    await createCallSession("secret-access-token");

    const [url, options] = fetchMock.mock.calls[0];
    expect(url).toBe("/api/auth/session");
    expect(url).not.toContain("secret-access-token");
    expect(options.headers.Authorization).toBe("Bearer secret-access-token");
    expect(JSON.parse(options.body)).not.toHaveProperty("accessToken");
  });

  it("buildCallSocketUrl places the opaque handle as a path segment, never a query parameter", () => {
    stubRequiredEnv("https://backend.example");
    const url = buildCallSocketUrl("/api/calls", "opaque-handle-xyz");
    expect(url).toBe("wss://backend.example/api/calls/opaque-handle-xyz");
    expect(url).not.toContain("?");
  });

  it("buildCallSocketUrl percent-encodes the opaque handle", () => {
    stubRequiredEnv("https://backend.example");
    const url = buildCallSocketUrl("/api/calls", "value with spaces");
    expect(url).toContain("value%20with%20spaces");
  });
});
