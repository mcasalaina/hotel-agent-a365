import { describe, expect, it } from "vitest";
import {
  callSessionReducer,
  initialCallSessionState,
  resolveConfirmation,
  type CallSessionState,
} from "./callSessionReducer";

function withMode(state: CallSessionState, mode: "voice" | "text" | "headless"): CallSessionState {
  return callSessionReducer(state, { type: "MODE_SELECTED", mode });
}

describe("callSessionReducer", () => {
  it("moves to the starting phase when a mode is selected", () => {
    const state = withMode(initialCallSessionState, "voice");
    expect(state.phase).toBe("starting");
    expect(state.mode).toBe("voice");
  });

  it("maps call_state messages to the matching UI phase", () => {
    const connecting = callSessionReducer(initialCallSessionState, {
      type: "SERVER_MESSAGE",
      message: { type: "call_state", state: "connecting" },
    });
    expect(connecting.phase).toBe("connecting");

    const connected = callSessionReducer(connecting, {
      type: "SERVER_MESSAGE",
      message: { type: "call_state", state: "connected" },
    });
    expect(connected.phase).toBe("active");

    const ended = callSessionReducer(connected, {
      type: "SERVER_MESSAGE",
      message: { type: "call_state", state: "ended" },
    });
    expect(ended.phase).toBe("ended");
  });

  it("resets the reconnect attempt counter once reconnected", () => {
    const reconnecting = callSessionReducer(initialCallSessionState, {
      type: "RECONNECT_ATTEMPT",
      attempt: 2,
    });
    expect(reconnecting.reconnectAttempt).toBe(2);

    const reconnected = callSessionReducer(reconnecting, {
      type: "SERVER_MESSAGE",
      message: { type: "call_state", state: "connected" },
    });
    expect(reconnected.reconnectAttempt).toBe(0);
  });

  it("appends a new transcript entry for a final utterance", () => {
    const state = callSessionReducer(initialCallSessionState, {
      type: "SERVER_MESSAGE",
      message: { type: "transcript", speaker: "user", text: "Hello", isFinal: true, timestamp: "t1" },
    });
    expect(state.transcripts).toHaveLength(1);
    expect(state.transcripts[0]).toMatchObject({ speaker: "user", text: "Hello", isFinal: true });
  });

  it("updates an open partial transcript entry in place instead of appending", () => {
    const partial = callSessionReducer(initialCallSessionState, {
      type: "SERVER_MESSAGE",
      message: { type: "transcript", speaker: "agent", text: "Look", isFinal: false, timestamp: "t1" },
    });
    const updated = callSessionReducer(partial, {
      type: "SERVER_MESSAGE",
      message: {
        type: "transcript",
        speaker: "agent",
        text: "Looking it up",
        isFinal: true,
        timestamp: "t2",
      },
    });
    expect(updated.transcripts).toHaveLength(1);
    expect(updated.transcripts[0].text).toBe("Looking it up");
    expect(updated.transcripts[0].isFinal).toBe(true);
  });

  it("keeps separate speakers' partial entries independent", () => {
    let state = callSessionReducer(initialCallSessionState, {
      type: "SERVER_MESSAGE",
      message: { type: "transcript", speaker: "user", text: "Hi", isFinal: false, timestamp: "t1" },
    });
    state = callSessionReducer(state, {
      type: "SERVER_MESSAGE",
      message: { type: "transcript", speaker: "agent", text: "Hello", isFinal: false, timestamp: "t2" },
    });
    expect(state.transcripts).toHaveLength(2);
  });

  it("accumulates timeline events, confirmations, and result cards", () => {
    let state = callSessionReducer(initialCallSessionState, {
      type: "SERVER_MESSAGE",
      message: { type: "timeline_event", category: "tool", message: "Checking rooms", timestamp: "t1" },
    });
    state = callSessionReducer(state, {
      type: "SERVER_MESSAGE",
      message: {
        type: "confirmation_request",
        confirmationId: "c1",
        summary: "Change room?",
        details: { Room: "Suite" },
        timestamp: "t2",
      },
    });
    state = callSessionReducer(state, {
      type: "SERVER_MESSAGE",
      message: {
        type: "result_card",
        cardType: "reservation",
        title: "Updated",
        fields: { Room: "Suite" },
        timestamp: "t3",
      },
    });

    expect(state.timeline).toHaveLength(1);
    expect(state.confirmations).toHaveLength(1);
    expect(state.confirmations[0].resolvedApproved).toBeNull();
    expect(state.resultCards).toHaveLength(1);
  });

  it("resolves a confirmation by id via resolveConfirmation", () => {
    const withConfirmation = callSessionReducer(initialCallSessionState, {
      type: "SERVER_MESSAGE",
      message: {
        type: "confirmation_request",
        confirmationId: "c1",
        summary: "Change room?",
        details: {},
        timestamp: "t1",
      },
    });
    const resolved = resolveConfirmation(withConfirmation, "c1", true);
    expect(resolved.confirmations[0].resolvedApproved).toBe(true);
  });

  it("dispatches CONFIRMATION_RESOLVED the same way", () => {
    const withConfirmation = callSessionReducer(initialCallSessionState, {
      type: "SERVER_MESSAGE",
      message: {
        type: "confirmation_request",
        confirmationId: "c1",
        summary: "Change room?",
        details: {},
        timestamp: "t1",
      },
    });
    const resolved = callSessionReducer(withConfirmation, {
      type: "CONFIRMATION_RESOLVED",
      confirmationId: "c1",
      approved: false,
    });
    expect(resolved.confirmations[0].resolvedApproved).toBe(false);
  });

  it("records a sanitized local error without leaking internals", () => {
    const state = callSessionReducer(initialCallSessionState, {
      type: "LOCAL_ERROR",
      message: "The call connection had a problem.",
    });
    expect(state.phase).toBe("error");
    expect(state.errorMessage).toBe("The call connection had a problem.");
  });

  it("RESET returns to the initial state", () => {
    const dirty = withMode(initialCallSessionState, "text");
    const reset = callSessionReducer(dirty, { type: "RESET" });
    expect(reset).toEqual(initialCallSessionState);
  });
});
