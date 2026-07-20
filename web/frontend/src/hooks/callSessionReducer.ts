/**
 * Pure state reducer for an in-progress simulated call. Kept separate from the orchestrating
 * hook so it can be unit tested without any WebSocket, MSAL, or Web Audio dependencies.
 */
import type {
  CallState,
  DispositionOutcome,
  ResultCardType,
  ServerCallMessage,
  TimelineEventCategory,
} from "../types/protocol";

export type CallPhase =
  | "idle"
  | "starting"
  | "connecting"
  | "active"
  | "reconnecting"
  | "ended"
  | "error";

export type CallMode = "voice" | "text" | "headless" | "prerecorded";

export interface TranscriptEntry {
  id: string;
  speaker: "user" | "agent";
  text: string;
  isFinal: boolean;
  timestamp: string;
}

export interface TimelineEntry {
  id: string;
  category: TimelineEventCategory;
  message: string;
  timestamp: string;
}

export interface ConfirmationEntry {
  id: string;
  confirmationId: string;
  summary: string;
  details: Record<string, string>;
  timestamp: string;
  resolvedApproved: boolean | null;
}

export interface ResultCardEntry {
  id: string;
  cardType: ResultCardType;
  title: string;
  fields: Record<string, string>;
  timestamp: string;
}

export interface DispositionInfo {
  outcome: DispositionOutcome;
  summary: string;
  timestamp: string;
}

export interface CallSessionState {
  phase: CallPhase;
  mode: CallMode | null;
  micMuted: boolean;
  reconnectAttempt: number;
  agentSessionId: string | null;
  lastCallState: CallState | null;
  transcripts: TranscriptEntry[];
  timeline: TimelineEntry[];
  confirmations: ConfirmationEntry[];
  resultCards: ResultCardEntry[];
  disposition: DispositionInfo | null;
  errorMessage: string | null;
}

export const initialCallSessionState: CallSessionState = {
  phase: "idle",
  mode: null,
  micMuted: false,
  reconnectAttempt: 0,
  agentSessionId: null,
  lastCallState: null,
  transcripts: [],
  timeline: [],
  confirmations: [],
  resultCards: [],
  disposition: null,
  errorMessage: null,
};

export type CallSessionAction =
  | { type: "RESET" }
  | { type: "PHASE_CHANGE"; phase: CallPhase }
  | { type: "MODE_SELECTED"; mode: CallMode }
  | { type: "SET_MIC_MUTED"; muted: boolean }
  | { type: "RECONNECT_ATTEMPT"; attempt: number }
  | { type: "SERVER_MESSAGE"; message: ServerCallMessage }
  | { type: "CONFIRMATION_RESOLVED"; confirmationId: string; approved: boolean }
  | { type: "LOCAL_ERROR"; message: string };

function nextId(prefix: string): string {
  return `${prefix}-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
}

function applyTranscript(
  transcripts: TranscriptEntry[],
  incoming: Extract<ServerCallMessage, { type: "transcript" }>,
): TranscriptEntry[] {
  const lastIndex = [...transcripts].reverse().findIndex((entry) => entry.speaker === incoming.speaker && !entry.isFinal);
  if (lastIndex === -1) {
    return [
      ...transcripts,
      {
        id: nextId("transcript"),
        speaker: incoming.speaker,
        text: incoming.text,
        isFinal: incoming.isFinal,
        timestamp: incoming.timestamp,
      },
    ];
  }
  const realIndex = transcripts.length - 1 - lastIndex;
  const updated = [...transcripts];
  updated[realIndex] = {
    ...updated[realIndex],
    text: incoming.text,
    isFinal: incoming.isFinal,
    timestamp: incoming.timestamp,
  };
  return updated;
}

function callStateToPhase(state: CallState): CallPhase {
  switch (state) {
    case "connecting":
      return "connecting";
    case "connected":
      return "active";
    case "reconnecting":
      return "reconnecting";
    case "ended":
      return "ended";
    case "error":
      return "error";
    default:
      return "active";
  }
}

export function callSessionReducer(
  state: CallSessionState,
  action: CallSessionAction,
): CallSessionState {
  switch (action.type) {
    case "RESET":
      return initialCallSessionState;

    case "PHASE_CHANGE":
      return { ...state, phase: action.phase };

    case "MODE_SELECTED":
      return { ...state, mode: action.mode, phase: "starting" };

    case "SET_MIC_MUTED":
      return { ...state, micMuted: action.muted };

    case "RECONNECT_ATTEMPT":
      return { ...state, reconnectAttempt: action.attempt, phase: "reconnecting" };

    case "LOCAL_ERROR":
      return { ...state, phase: "error", errorMessage: action.message };

    case "CONFIRMATION_RESOLVED":
      return resolveConfirmation(state, action.confirmationId, action.approved);

    case "SERVER_MESSAGE": {
      const message = action.message;
      switch (message.type) {
        case "auth_ack":
          return { ...state, agentSessionId: message.agentSessionId };

        case "call_state":
          return {
            ...state,
            lastCallState: message.state,
            phase: callStateToPhase(message.state),
            reconnectAttempt: message.state === "connected" ? 0 : state.reconnectAttempt,
            errorMessage: message.state === "error" ? (message.reason ?? state.errorMessage) : state.errorMessage,
          };

        case "transcript":
          return { ...state, transcripts: applyTranscript(state.transcripts, message) };

        case "timeline_event":
          return {
            ...state,
            timeline: [
              ...state.timeline,
              {
                id: nextId("timeline"),
                category: message.category,
                message: message.message,
                timestamp: message.timestamp,
              },
            ],
          };

        case "confirmation_request":
          return {
            ...state,
            confirmations: [
              ...state.confirmations,
              {
                id: nextId("confirmation"),
                confirmationId: message.confirmationId,
                summary: message.summary,
                details: message.details,
                timestamp: message.timestamp,
                resolvedApproved: null,
              },
            ],
          };

        case "result_card":
          return {
            ...state,
            resultCards: [
              ...state.resultCards,
              {
                id: nextId("result"),
                cardType: message.cardType,
                title: message.title,
                fields: message.fields,
                timestamp: message.timestamp,
              },
            ],
          };

        case "disposition":
          return {
            ...state,
            disposition: {
              outcome: message.outcome,
              summary: message.summary,
              timestamp: message.timestamp,
            },
          };

        case "error":
          return { ...state, errorMessage: message.message };

        default:
          return state;
      }
    }

    default:
      return state;
  }
}

/** Marks a confirmation as resolved locally (optimistic UI update after sending the response). */
export function resolveConfirmation(
  state: CallSessionState,
  confirmationId: string,
  approved: boolean,
): CallSessionState {
  return {
    ...state,
    confirmations: state.confirmations.map((entry) =>
      entry.confirmationId === confirmationId ? { ...entry, resolvedApproved: approved } : entry,
    ),
  };
}
