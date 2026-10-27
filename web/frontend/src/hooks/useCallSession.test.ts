import { act, renderHook, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { CallSocketCallbacks } from "../lib/callSocket";
import type { ClientCallMessage } from "../types/protocol";
import { useCallSession } from "./useCallSession";

const mocks = vi.hoisted(() => ({
  token: vi.fn(),
  createSession: vi.fn(),
  config: vi.fn(),
  audioFrame: vi.fn(),
  audioCommit: vi.fn(),
  close: vi.fn(),
  pcm: new ArrayBuffer(8),
  sockets: [] as { auth: ClientCallMessage; callbacks: CallSocketCallbacks }[],
}));

vi.mock("../auth/authContext", () => ({
  useAuth: () => ({ acquireApiToken: mocks.token }),
}));
vi.mock("../lib/backendClient", () => ({
  fetchBackendConfig: mocks.config,
  createCallSession: mocks.createSession,
  buildCallSocketUrl: () => "wss://hotel.example/api/calls",
}));
vi.mock("../lib/callSocket", () => ({
  CallSocket: class {
    constructor(_url: string, auth: ClientCallMessage, callbacks: CallSocketCallbacks) {
      mocks.sockets.push({ auth, callbacks });
    }
    connect() {}
    close = mocks.close;
    sendEndCall() {}
    sendAudioFrame = mocks.audioFrame;
    sendAudioCommit = mocks.audioCommit;
  },
}));
vi.mock("../lib/audioPlayback", () => ({
  AudioPlaybackQueue: class {
    dispose() {}
    enqueue() {}
  },
}));
vi.mock("../lib/wav", () => ({
  decodePcmWave: () => mocks.pcm,
  chunkPcm16: () => [mocks.pcm],
}));

async function ready() {
  const hook = renderHook(() => useCallSession());
  await waitFor(() => expect(hook.result.current.config).not.toBeNull());
  return hook;
}

describe("call session identity", () => {
  beforeEach(() => {
    vi.resetAllMocks();
    mocks.sockets.length = 0;
    mocks.token.mockResolvedValue("test-token");
    mocks.config.mockResolvedValue({
      features: { voiceEnabled: true, textEnabled: true, prerecordedAudioEnabled: true, offlinePlaybackEnabled: false },
      websocketPath: "/api/calls",
      maxReconnectAttempts: 3,
      reconnectBackoffMs: 1,
    });
    mocks.createSession
      .mockResolvedValueOnce({ sessionHandle: "handle-one", agentSessionId: "session-one", expiresAt: "future" })
      .mockResolvedValueOnce({ sessionHandle: "handle-two", agentSessionId: "session-two", expiresAt: "future" });
  });
  afterEach(() => vi.useRealTimers());

  it("binds a second prerecorded call to its own handle and session, never the ended text call", async () => {
    const { result } = await ready();
    await act(() => result.current.startCall("text"));
    act(() => {
      mocks.sockets[0].callbacks.onMessage({ type: "auth_ack", agentSessionId: "session-one" });
      mocks.sockets[0].callbacks.onMessage({
        type: "transcript", speaker: "user", text: "Previous guest", isFinal: true, timestamp: "t1",
      });
    });
    act(() => result.current.endCall());
    const file = new File(["question"], "question.wav", { type: "audio/wav" });
    Object.defineProperty(file, "arrayBuffer", { value: async () => mocks.pcm });
    await act(() => result.current.startPrerecorded(file));
    expect(mocks.sockets[1].auth).toEqual({
      type: "auth", mode: "prerecorded", opaqueHandle: "handle-two", agentSessionId: "session-two",
    });
    expect(result.current.state.transcripts).toEqual([]);
    act(() => mocks.sockets[1].callbacks.onMessage({ type: "auth_ack", agentSessionId: "session-two" }));
    expect(mocks.audioFrame).toHaveBeenCalledWith(mocks.pcm);
    expect(mocks.audioCommit).toHaveBeenCalledOnce();
    expect(result.current.state.agentSessionId).toBe("session-two");
  });

  it("retains a call's exact session pair during reconnect and cancels its retry on a new call", async () => {
    const { result } = await ready();
    vi.useFakeTimers();
    await act(() => result.current.startCall("text"));
    act(() => mocks.sockets[0].callbacks.onSocketError("Disconnected"));
    act(() => vi.advanceTimersByTime(1));
    expect(mocks.sockets[1].auth).toEqual(mocks.sockets[0].auth);
    act(() => mocks.sockets[1].callbacks.onSocketError("Disconnected again"));
    await act(() => result.current.startCall("text"));
    act(() => vi.advanceTimersByTime(100));
    expect(mocks.sockets).toHaveLength(3);
    expect(mocks.sockets[2].auth).toEqual({
      type: "auth", mode: "text", opaqueHandle: "handle-two", agentSessionId: "session-two",
    });
    expect(mocks.createSession).toHaveBeenCalledTimes(2);
    expect(mocks.close).toHaveBeenCalled();
  });
});
