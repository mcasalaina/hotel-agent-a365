import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { CallSocket } from "./callSocket";

/** Minimal WebSocket stub that records what was sent and lets tests drive lifecycle events. */
class FakeWebSocket {
  static instances: FakeWebSocket[] = [];
  static OPEN = 1;

  binaryType = "blob";
  readyState = 0;
  sent: Array<string | ArrayBuffer> = [];
  listeners: Record<string, Array<(event: unknown) => void>> = {};
  url: string;

  constructor(url: string) {
    this.url = url;
    FakeWebSocket.instances.push(this);
  }

  addEventListener(type: string, listener: (event: unknown) => void) {
    (this.listeners[type] ??= []).push(listener);
  }

  send(data: string | ArrayBuffer) {
    this.sent.push(data);
  }

  close() {
    this.readyState = 3;
    this.emit("close", {});
  }

  emit(type: string, event: unknown) {
    for (const listener of this.listeners[type] ?? []) {
      listener(event);
    }
  }

  triggerOpen() {
    this.readyState = FakeWebSocket.OPEN;
    this.emit("open", {});
  }

  triggerClose(code: number) {
    this.readyState = 3;
    this.emit("close", { code });
  }
}

describe("CallSocket", () => {
  beforeEach(() => {
    FakeWebSocket.instances = [];
    vi.stubGlobal("WebSocket", FakeWebSocket as unknown as typeof WebSocket);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("sends the auth frame as the first message once the socket opens", () => {
    const onStatusChange = vi.fn();
    const socket = new CallSocket(
      "wss://backend.example/api/calls",
      { type: "auth", opaqueHandle: "opaque-handle-123", mode: "text" },
      {
        onMessage: vi.fn(),
        onAudioFrame: vi.fn(),
        onStatusChange,
        onSocketError: vi.fn(),
      },
    );

    socket.connect();
    const fake = FakeWebSocket.instances[0];
    expect(fake.url).not.toContain("opaque-handle-123");
    fake.triggerOpen();

    expect(fake.sent).toHaveLength(1);
    const firstFrame = JSON.parse(fake.sent[0] as string);
    expect(firstFrame).toEqual({ type: "auth", opaqueHandle: "opaque-handle-123", mode: "text" });
    expect(onStatusChange).toHaveBeenCalledWith("open");
  });

  it("never sends the opaque handle or an access token in the socket URL", () => {
    const socket = new CallSocket(
      "wss://backend.example/api/calls",
      { type: "auth", opaqueHandle: "opaque-handle-123", mode: "voice" },
      { onMessage: vi.fn(), onAudioFrame: vi.fn(), onStatusChange: vi.fn(), onSocketError: vi.fn() },
    );
    socket.connect();
    const fake = FakeWebSocket.instances[0];
    expect(fake.url).not.toContain("opaque-handle-123");
    expect(fake.url).not.toContain("?");
    expect(fake.url).not.toContain("access_token");
  });

  it("routes text frames through the parser and binary frames to onAudioFrame", () => {
    const onMessage = vi.fn();
    const onAudioFrame = vi.fn();
    const socket = new CallSocket(
      "wss://backend.example/api/calls",
      { type: "auth", opaqueHandle: "h1", mode: "voice" },
      { onMessage, onAudioFrame, onStatusChange: vi.fn(), onSocketError: vi.fn() },
    );
    socket.connect();
    const fake = FakeWebSocket.instances[0];
    fake.triggerOpen();

    fake.emit("message", { data: JSON.stringify({ type: "call_state", state: "connected" }) });
    expect(onMessage).toHaveBeenCalledWith({ type: "call_state", state: "connected" });

    const audioBuffer = new ArrayBuffer(4);
    fake.emit("message", { data: audioBuffer });
    expect(onAudioFrame).toHaveBeenCalledWith(audioBuffer);
  });

  it("drops unparseable or unknown-type text frames without throwing", () => {
    const onMessage = vi.fn();
    const onSocketError = vi.fn();
    const socket = new CallSocket(
      "wss://backend.example/api/calls",
      { type: "auth", opaqueHandle: "h1", mode: "text" },
      { onMessage, onAudioFrame: vi.fn(), onStatusChange: vi.fn(), onSocketError },
    );
    socket.connect();
    const fake = FakeWebSocket.instances[0];
    fake.triggerOpen();

    fake.emit("message", { data: "not json" });
    expect(onSocketError).toHaveBeenCalled();
    expect(onMessage).not.toHaveBeenCalled();

    fake.emit("message", { data: JSON.stringify({ type: "unknown_future_event" }) });
    expect(onMessage).not.toHaveBeenCalled();
  });

  it("sends a cancel_output frame for barge-in without any rollback claim in the payload", () => {
    const socket = new CallSocket(
      "wss://backend.example/api/calls",
      { type: "auth", opaqueHandle: "h1", mode: "voice" },
      { onMessage: vi.fn(), onAudioFrame: vi.fn(), onStatusChange: vi.fn(), onSocketError: vi.fn() },
    );
    socket.connect();
    const fake = FakeWebSocket.instances[0];
    fake.triggerOpen();
    fake.sent = [];

    socket.sendCancelOutput();
    expect(JSON.parse(fake.sent[0] as string)).toEqual({ type: "cancel_output" });
  });

  it("only sends binary audio frames while the socket is open", () => {
    const socket = new CallSocket(
      "wss://backend.example/api/calls",
      { type: "auth", opaqueHandle: "h1", mode: "voice" },
      { onMessage: vi.fn(), onAudioFrame: vi.fn(), onStatusChange: vi.fn(), onSocketError: vi.fn() },
    );
    socket.connect();
    const fake = FakeWebSocket.instances[0];
    const frame = new ArrayBuffer(2);

    socket.sendAudioFrame(frame); // not open yet
    expect(fake.sent).toHaveLength(0);

    fake.triggerOpen();
    fake.sent = [];
    socket.sendAudioFrame(frame);
    expect(fake.sent).toEqual([frame]);
  });

  it("reports an unexpected close once and ignores an intentional close", () => {
    const onSocketError = vi.fn();
    const socket = new CallSocket(
      "wss://backend.example/api/calls",
      { type: "auth", opaqueHandle: "h1", mode: "voice" },
      { onMessage: vi.fn(), onAudioFrame: vi.fn(), onStatusChange: vi.fn(), onSocketError },
    );
    socket.connect();
    const fake = FakeWebSocket.instances[0];
    fake.emit("error", {});
    fake.triggerClose(1006);
    expect(onSocketError).toHaveBeenCalledTimes(1);

    const intentional = new CallSocket(
      "wss://backend.example/api/calls",
      { type: "auth", opaqueHandle: "h2", mode: "voice" },
      { onMessage: vi.fn(), onAudioFrame: vi.fn(), onStatusChange: vi.fn(), onSocketError },
    );
    intentional.connect();
    intentional.close();
    expect(onSocketError).toHaveBeenCalledTimes(1);
  });
});
