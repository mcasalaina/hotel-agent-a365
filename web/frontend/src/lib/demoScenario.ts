/**
 * Deterministic, scripted event stream used ONLY by explicit demo/headless mode. This never runs
 * in network mode -- when connected to the real backend, every event on screen comes from the
 * live `ServerCallMessage` stream over the call socket. This scenario exists so the UI, transcript,
 * timeline, confirmation, and result-card rendering can be validated without a microphone or a
 * running backend, per the Phase 3 headless/prerecorded test-mode requirement.
 *
 * All guest, reservation, and folio details below are synthetic and belong to the fictional
 * "Lyrenza Hotels" chain used throughout this demo.
 */
import type { ServerCallMessage } from "../types/protocol";

export interface ScriptedStep {
  /** Milliseconds to wait after the previous step before emitting this one. */
  delayMs: number;
  message: ServerCallMessage;
}

const iso = () => new Date().toISOString();

/** A full scripted call: guest asks about a reservation, agent looks it up, confirms a room
 * change, and wraps up. Used by the headless/demo mode toggle in the UI. */
export function buildDemoScenario(): ScriptedStep[] {
  return [
    {
      delayMs: 300,
      message: { type: "auth_ack", agentSessionId: "offline-session-0001" },
    },
    {
      delayMs: 200,
      message: { type: "call_state", state: "connected" },
    },
    {
      delayMs: 500,
      message: {
        type: "transcript",
        speaker: "user",
        text: "Hi, I'd like to check my upcoming reservation at the Lyrenza Bay Meridian.",
        isFinal: true,
        timestamp: iso(),
      },
    },
    {
      delayMs: 400,
      message: {
        type: "timeline_event",
        category: "progress",
        message: "Looking up your upcoming reservations now.",
        timestamp: iso(),
      },
    },
    {
      delayMs: 500,
      message: {
        type: "timeline_event",
        category: "data_source",
        message: "Offline walkthrough: displaying a prerecorded reservation lookup.",
        timestamp: iso(),
      },
    },
    {
      delayMs: 500,
      message: {
        type: "transcript",
        speaker: "agent",
        text:
          "This offline walkthrough shows Jordan Ellery checking in Friday for two nights in a " +
          "King Harbor View room at the Lyrenza Bay Meridian.",
        isFinal: true,
        timestamp: iso(),
      },
    },
    {
      delayMs: 500,
      message: {
        type: "transcript",
        speaker: "user",
        text: "Great, can you move that to a Deluxe Suite instead?",
        isFinal: true,
        timestamp: iso(),
      },
    },
    {
      delayMs: 400,
      message: {
        type: "timeline_event",
        category: "tool",
        message: "Checking Deluxe Suite availability for those dates.",
        timestamp: iso(),
      },
    },
    {
      delayMs: 600,
      message: {
        type: "confirmation_request",
        confirmationId: "offline-confirmation-0001",
        summary: "Show a Deluxe Suite room change in this offline walkthrough?",
        details: {
          Guest: "Jordan Ellery",
          Property: "Lyrenza Bay Meridian",
          "Check-in": "Friday",
          Nights: "2",
          "Current room": "King Harbor View",
          "New room": "Deluxe Suite",
          "Rate difference": "+$85.00/night",
        },
        timestamp: iso(),
      },
    },
    {
      delayMs: 900,
      message: {
        type: "timeline_event",
        category: "progress",
        message: "Offline walkthrough: displaying the room change. No hotel records are changed.",
        timestamp: iso(),
      },
    },
    {
      delayMs: 700,
      message: {
        type: "result_card",
        cardType: "reservation",
        title: "Offline reservation walkthrough",
        fields: {
          Guest: "Jordan Ellery",
          Property: "Lyrenza Bay Meridian",
          "Confirmation number": "LYR-OFFLINE-48213",
          Room: "Deluxe Suite",
          "Check-in": "Friday",
          "Check-out": "Sunday",
        },
        timestamp: iso(),
      },
    },
    {
      delayMs: 500,
      message: {
        type: "transcript",
        speaker: "agent",
        text: "The offline walkthrough now shows a Deluxe Suite. No hotel records were changed.",
        isFinal: true,
        timestamp: iso(),
      },
    },
    {
      delayMs: 400,
      message: {
        type: "transcript",
        speaker: "user",
        text: "No, that's everything, thank you.",
        isFinal: true,
        timestamp: iso(),
      },
    },
    {
      delayMs: 400,
      message: {
        type: "disposition",
        outcome: "resolved",
        summary: "Offline walkthrough complete. No hotel records were changed.",
        timestamp: iso(),
      },
    },
    {
      delayMs: 200,
      message: { type: "call_state", state: "ended" },
    },
  ];
}
