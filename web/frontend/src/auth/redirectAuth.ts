import { InMemoryWebStorage, UserManager, WebStorageStateStore } from "oidc-client-ts";
import { getAppEnvConfig } from "../config/appConfig";

let client: UserManager | undefined;

export function getRedirectAuthClient(): UserManager {
  if (!client) {
    const config = getAppEnvConfig();
    client = new UserManager({
      authority: `${config.entraAuthority.replace(/\/(?:v2\.0\/?)?$/, "")}/v2.0`,
      client_id: config.entraClientId,
      redirect_uri: `${window.location.origin}/`,
      response_type: "code",
      response_mode: "fragment",
      scope: `openid profile ${config.entraApiScope}`,
      disablePKCE: false,
      automaticSilentRenew: false,
      monitorSession: false,
      loadUserInfo: false,
      staleStateAgeInSeconds: 600,
      redirectMethod: "replace",
      redirectTarget: "self",
      userStore: new WebStorageStateStore({
        store: new InMemoryWebStorage(),
        prefix: "hotel.pkce.user.",
      }),
      // Only short-lived PKCE request state survives navigation, never tokens or user records.
      stateStore: new WebStorageStateStore({
        store: window.sessionStorage,
        prefix: "hotel.pkce.state.",
      }),
    });
  }
  return client;
}

export function isSameTabCallback(): boolean {
  const url = new URL(window.location.href);
  const params = new URLSearchParams(url.hash.slice(1));
  return params.has("state") && (params.has("code") || params.has("error"));
}

export async function completeSameTabSignIn() {
  const responseUrl = window.location.href;
  window.history.replaceState(window.history.state, "", window.location.pathname);
  return getRedirectAuthClient().signinRedirectCallback(responseUrl);
}
