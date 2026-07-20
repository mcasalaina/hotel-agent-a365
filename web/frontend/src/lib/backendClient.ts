/**
 * Thin HTTP client for the private backend proxy. This is the only network surface that ever
 * sees the signed-in user's Entra access token; the token is attached as a bearer header on a
 * single request and is never written to a URL, storage, or log.
 */
import { getAppEnvConfig } from "../config/appConfig";
import type {
  BackendConfigResponse,
  CreateSessionRequest,
  CreateSessionResponse,
} from "../types/protocol";

export class BackendRequestError extends Error {
  readonly status: number;

  constructor(message: string, status: number) {
    super(message);
    this.name = "BackendRequestError";
    this.status = status;
  }
}

function backendUrl(path: string): string {
  const base = getAppEnvConfig().backendBaseUrl;
  return base ? new URL(path, base).toString() : path;
}

/** GET /api/config -- public, non-secret runtime configuration. No auth required. */
export async function fetchBackendConfig(signal?: AbortSignal): Promise<BackendConfigResponse> {
  const response = await fetch(backendUrl("/api/config"), {
    method: "GET",
    headers: { Accept: "application/json" },
    signal,
  });
  if (!response.ok) {
    throw new BackendRequestError("Unable to load contact-center configuration.", response.status);
  }
  return (await response.json()) as BackendConfigResponse;
}

/**
 * POST /api/auth/session -- exchanges the signed-in user's Entra access token for a short-lived
 * opaque session handle. The handle (not the Entra token) is what the browser subsequently
 * presents to the call WebSocket.
 */
export async function createCallSession(
  accessToken: string,
  signal?: AbortSignal,
): Promise<CreateSessionResponse> {
  const body: CreateSessionRequest = { clientContext: "web" };
  const response = await fetch(backendUrl("/api/auth/session"), {
    method: "POST",
    headers: {
      Accept: "application/json",
      "Content-Type": "application/json",
      Authorization: `Bearer ${accessToken}`,
    },
    body: JSON.stringify(body),
    signal,
  });
  if (!response.ok) {
    throw new BackendRequestError("Unable to start a signed-in call session.", response.status);
  }
  return (await response.json()) as CreateSessionResponse;
}

/** Builds the fixed `wss://`/`ws://` call URL. Authentication is sent only in the first frame. */
export function buildCallSocketUrl(websocketPath: string): string {
  const base = getAppEnvConfig().backendBaseUrl;
  const path = websocketPath.replace(/\/$/, "");
  if (base) {
    const url = new URL(path, base);
    url.protocol = url.protocol === "https:" ? "wss:" : "ws:";
    return url.toString();
  }
  const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
  return `${protocol}//${window.location.host}${path}`;
}
