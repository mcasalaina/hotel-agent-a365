/**
 * Client wire protocol for the Lyrenza Hotels simulated contact-center backend proxy.
 *
 * This module documents every request/response shape exchanged between the browser and the
 * *private backend proxy* (never the Foundry service directly). All data in this demo represents
 * a fictional hotel chain and synthetic guests; nothing here is a real reservation system.
 *
 * -----------------------------------------------------------------------------------------------
 * Protocol assumption (documented deviation): the task brief lists the WebSocket route as
 * `/api/calls/{opaqueHandle}` (handle as a path segment), but also requires that the opaque
 * handle never appear in a query string and that a first JSON auth frame be preferred for
 * authentication because the browser `WebSocket` API cannot set headers. This client satisfies
 * both constraints at once: it opens the socket at `/api/calls/{opaqueHandle}` (the handle is a
 * path segment, not a query parameter, so it matches the literal route contract) and then, as the
 * very first frame sent after `onopen`, transmits a `ClientAuthFrame` that restates the handle.
 * The backend is expected to treat the connection as unauthenticated (queued, no call operations
 * permitted) until that first frame is received and validated, then bind the socket to the
 * signed-in subject for the remainder of its lifetime. If a future backend contract removes the
 * path segment entirely, only `buildCallSocketUrl` below needs to change.
 * -----------------------------------------------------------------------------------------------
 */

/** Response body for `GET /api/config`. Contains no secrets; safe to expose to the browser. */
export interface BackendConfigResponse {
  /** Deployment environment label, shown only in developer-facing surfaces. */
  environment: "development" | "staging" | "production";
  /** Display name of the fictional hotel brand, e.g. "Lyrenza Hotels". */
  hotelBrandName: string;
  /** Notice string the UI must render verbatim near any synthetic data. */
  syntheticDataNotice: string;
  /** Feature flags the backend currently supports. */
  features: {
    voiceEnabled: boolean;
    textEnabled: boolean;
    headlessDemoEnabled: boolean;
  };
  /** Path prefix (no host) used to construct the call WebSocket URL, e.g. "/api/calls". */
  websocketPath: string;
  /** Maximum automatic reconnect attempts the client should perform per dropped call. */
  maxReconnectAttempts: number;
  /** Base backoff delay in milliseconds between reconnect attempts (doubles each attempt). */
  reconnectBackoffMs: number;
}

/** Request body for `POST /api/auth/session`. The bearer Entra access token goes in the
 * `Authorization` header, never in this body. */
export interface CreateSessionRequest {
  /** Declares the client surface so the backend can apply channel-aware authorization rules. */
  clientContext: "web";
}

/** Response body for `POST /api/auth/session`. */
export interface CreateSessionResponse {
  /** Short-lived opaque handle. Kept in memory only; never persisted to storage. */
  sessionHandle: string;
  /** ISO-8601 timestamp when the handle expires and a new one must be requested. */
  expiresAt: string;
  /** Correlates reconnects to the same in-flight agent session, if one already exists. */
  agentSessionId?: string;
}

/** Discriminated union of every message the client sends to `/api/calls/{opaqueHandle}`. */
export type ClientCallMessage =
  | ClientAuthFrame
  | ClientTextTurnFrame
  | ClientMicStateFrame
  | ClientConfirmationResponseFrame
  | ClientCancelOutputFrame
  | ClientEndCallFrame;

/** Must be the first frame sent immediately after the socket opens. */
export interface ClientAuthFrame {
  type: "auth";
  opaqueHandle: string;
  /** Present when resuming a dropped call so the backend can restore session-visible status. */
  agentSessionId?: string;
  mode: "voice" | "text" | "headless";
}

/** A typed text turn, used in text-input mode and in headless/prerecorded test mode. */
export interface ClientTextTurnFrame {
  type: "text_turn";
  text: string;
  timestamp: string;
}

/** Reports local microphone mute state; does not stop the call. */
export interface ClientMicStateFrame {
  type: "mic_state";
  muted: boolean;
}

/** Guest's answer to a pending confirmation card (e.g. a reservation change). */
export interface ClientConfirmationResponseFrame {
  type: "confirmation_response";
  confirmationId: string;
  approved: boolean;
}

/** Barge-in signal: stop the agent's queued output audio/text. This is a playback-cancel
 * request only. It never claims to roll back a business mutation that has already committed. */
export interface ClientCancelOutputFrame {
  type: "cancel_output";
}

/** Guest-initiated hangup. */
export interface ClientEndCallFrame {
  type: "end_call";
}

/** Discriminated union of every JSON text message the server sends over the call socket.
 * Binary WebSocket frames received on the same socket are raw PCM16 24 kHz mono agent audio
 * and carry no envelope. */
export type ServerCallMessage =
  | ServerAuthAckMessage
  | ServerCallStateMessage
  | ServerTranscriptMessage
  | ServerTimelineEventMessage
  | ServerConfirmationRequestMessage
  | ServerResultCardMessage
  | ServerDispositionMessage
  | ServerErrorMessage;

export interface ServerAuthAckMessage {
  type: "auth_ack";
  agentSessionId: string;
}

export type CallState = "connecting" | "connected" | "reconnecting" | "ended" | "error";

export interface ServerCallStateMessage {
  type: "call_state";
  state: CallState;
  /** Short, user-safe reason; never a raw backend exception or stack trace. */
  reason?: string;
}

export interface ServerTranscriptMessage {
  type: "transcript";
  speaker: "user" | "agent";
  text: string;
  /** False while the utterance is still streaming in (partial); true on the final revision. */
  isFinal: boolean;
  timestamp: string;
}

export type TimelineEventCategory = "progress" | "tool" | "data_source";

/** A friendly, truthful status update -- never invented progress or hidden chain-of-thought. */
export interface ServerTimelineEventMessage {
  type: "timeline_event";
  category: TimelineEventCategory;
  message: string;
  timestamp: string;
}

export interface ServerConfirmationRequestMessage {
  type: "confirmation_request";
  confirmationId: string;
  summary: string;
  /** Plain label/value pairs to render in the confirmation card; no raw system identifiers. */
  details: Record<string, string>;
  timestamp: string;
}

export type ResultCardType = "reservation" | "folio" | "request";

export interface ServerResultCardMessage {
  type: "result_card";
  cardType: ResultCardType;
  title: string;
  fields: Record<string, string>;
  timestamp: string;
}

export type DispositionOutcome = "resolved" | "escalated" | "cancelled" | "error";

export interface ServerDispositionMessage {
  type: "disposition";
  outcome: DispositionOutcome;
  summary: string;
  timestamp: string;
}

/** Sanitized error surface. The backend is expected to strip stack traces, internal identifiers,
 * and credentials before sending this; the client renders `message` verbatim and nothing else. */
export interface ServerErrorMessage {
  type: "error";
  message: string;
  code?: string;
}

/** Narrow an unknown parsed JSON payload down to a `ServerCallMessage`, or return `null` if the
 * payload does not look like a message this client understands. Unknown `type` values are
 * dropped defensively instead of throwing, so a backend rollout of a new event type never
 * crashes the UI. */
export function parseServerCallMessage(payload: unknown): ServerCallMessage | null {
  if (typeof payload !== "object" || payload === null || !("type" in payload)) {
    return null;
  }
  const knownTypes: ReadonlySet<ServerCallMessage["type"]> = new Set([
    "auth_ack",
    "call_state",
    "transcript",
    "timeline_event",
    "confirmation_request",
    "result_card",
    "disposition",
    "error",
  ]);
  const candidate = payload as { type: unknown };
  if (typeof candidate.type === "string" && knownTypes.has(candidate.type as ServerCallMessage["type"])) {
    return payload as ServerCallMessage;
  }
  return null;
}
