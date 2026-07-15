/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** Entra application (client) ID registered as a public client (Authorization Code + PKCE). */
  readonly VITE_ENTRA_CLIENT_ID: string;
  /** Entra authority URL, e.g. https://login.microsoftonline.com/<tenant-id>. */
  readonly VITE_ENTRA_AUTHORITY: string;
  /** Redirect URI registered on the Entra app registration for this SPA. */
  readonly VITE_ENTRA_REDIRECT_URI: string;
  /** Space-separated delegated scope(s) requested for the hotel agent API, e.g.
   * "api://<api-app-id>/HotelAgent.Access". */
  readonly VITE_ENTRA_API_SCOPE: string;
  /** Origin of the private backend proxy, e.g. "https://localhost:8443". Same-origin deployments
   * may leave this empty to use relative paths. */
  readonly VITE_BACKEND_BASE_URL?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
