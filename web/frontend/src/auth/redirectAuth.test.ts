import { afterEach, describe, expect, it, vi } from "vitest";
import { User } from "oidc-client-ts";
import { completeSameTabSignIn, getRedirectAuthClient, isSameTabCallback } from "./redirectAuth";

vi.mock("../config/appConfig", () => ({
  getAppEnvConfig: () => ({
    entraAuthority: "https://login.microsoftonline.com/tenant",
    entraClientId: "spa-client",
    entraApiScope: "api://hotel/HotelAgent.Access",
  }),
}));

describe("same-tab PKCE configuration", () => {
  afterEach(async () => {
    await getRedirectAuthClient().removeUser();
    sessionStorage.clear();
    history.replaceState(null, "", "/");
  });

  it("uses code and PKCE without popup, refresh-token scope or automatic renewal", () => {
    const { settings } = getRedirectAuthClient();
    expect(settings.authority).toBe("https://login.microsoftonline.com/tenant/v2.0");
    expect(settings.redirect_uri).toBe(`${location.origin}/`);
    expect(settings.response_type).toBe("code");
    expect(settings.response_mode).toBe("fragment");
    expect(settings.disablePKCE).toBe(false);
    expect(settings.automaticSilentRenew).toBe(false);
    expect(settings.scope).toBe("openid profile api://hotel/HotelAgent.Access");
    expect(settings.redirectTarget).toBe("self");
  });

  it("stores tokens and user records only in memory", async () => {
    const client = getRedirectAuthClient();
    const user = new User({
      access_token: "test-access-token",
      id_token: "test-id-token",
      token_type: "Bearer",
      scope: client.settings.scope,
      profile: { iss: client.settings.authority, sub: "operator", aud: "spa-client", exp: 9999999999, iat: 1 },
    });
    await client.storeUser(user);
    expect((await client.getUser())?.access_token).toBe("test-access-token");
    expect(sessionStorage.length).toBe(0);
    expect(localStorage.length).toBe(0);
  });

  it("uses separate session storage only for transient request state", async () => {
    await getRedirectAuthClient().settings.stateStore.set("request", "pkce-request-state");
    expect(sessionStorage.getItem("hotel.pkce.state.request")).toBe("pkce-request-state");
    expect(localStorage.length).toBe(0);
  });

  it("recognizes authorization callbacks, not ordinary application fragments", () => {
    history.replaceState(null, "", "/#code=one-time-code&state=known-request");
    expect(isSameTabCallback()).toBe(true);
    history.replaceState(null, "", "/#reservations");
    expect(isSameTabCallback()).toBe(false);
  });

  it("removes callback parameters and rejects unknown authorization state", async () => {
    history.replaceState(null, "", "/#code=one-time-code&state=unknown-request");
    await expect(completeSameTabSignIn()).rejects.toThrow("No matching state found in storage");
    expect(location.hash).toBe("");
    expect(location.search).toBe("");
  });
});
