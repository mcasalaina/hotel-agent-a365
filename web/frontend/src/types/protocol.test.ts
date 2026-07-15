import { describe, expect, it } from "vitest";
import { parseServerCallMessage } from "./protocol";

describe("parseServerCallMessage", () => {
  it("accepts every known server message type", () => {
    const samples: unknown[] = [
      { type: "auth_ack", agentSessionId: "abc" },
      { type: "call_state", state: "connected" },
      { type: "transcript", speaker: "user", text: "hi", isFinal: true, timestamp: "t" },
      { type: "timeline_event", category: "progress", message: "m", timestamp: "t" },
      {
        type: "confirmation_request",
        confirmationId: "c1",
        summary: "s",
        details: {},
        timestamp: "t",
      },
      { type: "result_card", cardType: "reservation", title: "t", fields: {}, timestamp: "t" },
      { type: "disposition", outcome: "resolved", summary: "s", timestamp: "t" },
      { type: "error", message: "sanitized message" },
    ];
    for (const sample of samples) {
      expect(parseServerCallMessage(sample)).toEqual(sample);
    }
  });

  it("rejects payloads with an unknown type instead of throwing", () => {
    expect(parseServerCallMessage({ type: "not_a_real_type" })).toBeNull();
  });

  it("rejects non-object and type-less payloads", () => {
    expect(parseServerCallMessage(null)).toBeNull();
    expect(parseServerCallMessage("a string")).toBeNull();
    expect(parseServerCallMessage(42)).toBeNull();
    expect(parseServerCallMessage({})).toBeNull();
  });
});
