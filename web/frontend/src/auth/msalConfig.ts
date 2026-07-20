/**
 * Microsoft Entra sign-in configuration.
 *
 * Uses @azure/msal-browser's Authorization Code flow with PKCE (the only flow msal-browser
 * implements for SPAs). The redirect URI points to the dedicated MSAL v5 bridge entry
 * (`redirect.html`), which relays popup and silent-flow responses to this page. Tokens are kept in
 * memory only:
 *   - `cacheLocation: "memoryStorage"` keeps durable token/account state out of Web Storage.
 *     MSAL uses sessionStorage only for ephemeral request metadata during an active auth flow, as
 *     required by its redirect bridge. A full page reload requires a fresh interactive or silent
 *     (iframe) sign-in.
 *   - No custom code in this app writes tokens or the opaque call-session handle to any Web
 *     Storage or cookie.
 */
import { PublicClientApplication, type Configuration, LogLevel } from "@azure/msal-browser";
import { getAppEnvConfig } from "../config/appConfig";

export function buildMsalConfig(): Configuration {
  const env = getAppEnvConfig();
  return {
    auth: {
      clientId: env.entraClientId,
      authority: env.entraAuthority,
      redirectUri: env.entraRedirectUri,
    },
    cache: {
      // Durable tokens and accounts remain in memory. MSAL v5 independently uses sessionStorage
      // for short-lived request metadata needed by the redirect bridge.
      cacheLocation: "memoryStorage",
    },
    system: {
      loggerOptions: {
        loggerCallback: (level, message, containsPii) => {
          if (containsPii) {
            return;
          }
          if (level === LogLevel.Error) {
            // eslint-disable-next-line no-console
            console.error(`[msal] ${message}`);
          }
        },
        logLevel: LogLevel.Warning,
      },
    },
  };
}

/** The delegated scopes requested for the hotel agent API, derived from Vite env config. */
export function apiLoginScopes(): string[] {
  const env = getAppEnvConfig();
  return env.entraApiScope
    .split(/\s+/)
    .map((scope) => scope.trim())
    .filter((scope) => scope.length > 0);
}

let msalInstance: PublicClientApplication | null = null;

/** Lazily constructs a single shared `PublicClientApplication` for the app lifetime. */
export function getMsalInstance(): PublicClientApplication {
  if (!msalInstance) {
    msalInstance = new PublicClientApplication(buildMsalConfig());
  }
  return msalInstance;
}
