/**
 * Runtime configuration derived from build-time Vite environment variables. No secrets are read
 * here: only public client identifiers, authority URLs, and a backend base URL are needed to
 * begin the Authorization Code + PKCE sign-in flow.
 */

export interface AppEnvConfig {
  entraClientId: string;
  entraAuthority: string;
  entraRedirectUri: string;
  entraApiScope: string;
  backendBaseUrl: string;
}

class MissingEnvVarError extends Error {
  constructor(name: string) {
    super(
      `Missing required environment variable ${name}. Copy web/frontend/.env.example to ` +
        `web/frontend/.env.local and fill in your Entra app registration values.`,
    );
    this.name = "MissingEnvVarError";
  }
}

function requireEnv(name: string, value: string | undefined): string {
  if (!value || value.trim().length === 0) {
    throw new MissingEnvVarError(name);
  }
  return value;
}

let cachedConfig: AppEnvConfig | null = null;

/** Reads and validates the Vite-provided environment configuration exactly once per page load. */
export function getAppEnvConfig(): AppEnvConfig {
  if (cachedConfig) {
    return cachedConfig;
  }
  const env = import.meta.env;
  cachedConfig = {
    entraClientId: requireEnv("VITE_ENTRA_CLIENT_ID", env.VITE_ENTRA_CLIENT_ID),
    entraAuthority: requireEnv("VITE_ENTRA_AUTHORITY", env.VITE_ENTRA_AUTHORITY),
    entraRedirectUri: requireEnv("VITE_ENTRA_REDIRECT_URI", env.VITE_ENTRA_REDIRECT_URI),
    entraApiScope: requireEnv("VITE_ENTRA_API_SCOPE", env.VITE_ENTRA_API_SCOPE),
    backendBaseUrl: env.VITE_BACKEND_BASE_URL?.trim() ?? "",
  };
  return cachedConfig;
}

/** Test-only hook to reset the memoized config between unit tests. */
export function __resetAppEnvConfigForTests(): void {
  cachedConfig = null;
}
