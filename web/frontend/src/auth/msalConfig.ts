/**
 * Microsoft Entra sign-in configuration.
 *
 * Uses @azure/msal-browser's Authorization Code flow with PKCE (the only flow msal-browser
 * implements for SPAs). Tokens are kept in memory only:
 *   - `cacheLocation: "memoryStorage"` means MSAL never touches localStorage, sessionStorage, or
 *     cookies for token/account state. A full page reload requires a fresh interactive or silent
 *     (iframe) sign-in; this is an intentional trade-off for the "tokens in memory only"
 *     requirement.
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
      // In-memory only. Never persist tokens to browser storage or cookies. This msal-browser
      // version has no cookie-backed auth-state option, so there is nothing else to disable here.
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
