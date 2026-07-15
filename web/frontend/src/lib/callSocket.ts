/**
 * Typed WebSocket client for `/api/calls/{opaqueHandle}` on the private backend proxy. This
 * client never connects to Foundry directly and never places the Entra access token or the
 * opaque session handle in a query string; see the protocol note at the top of
 * `types/protocol.ts` for how the handle is transmitted.
 */
import {
  parseServerCallMessage,
  type ClientCallMessage,
  type ServerCallMessage,
} from "../types/protocol";

export type CallSocketStatus = "connecting" | "open" | "closed";

export interface CallSocketCallbacks {
  onMessage: (message: ServerCallMessage) => void;
  onAudioFrame: (frame: ArrayBuffer) => void;
  onStatusChange: (status: CallSocketStatus) => void;
  /** A user-safe connection problem description; never a raw error object. */
  onSocketError: (message: string) => void;
}

export class CallSocket {
  private socket: WebSocket | null = null;
  private status: CallSocketStatus = "closed";
  private readonly url: string;
  private readonly authFrame: ClientCallMessage;
  private readonly callbacks: CallSocketCallbacks;

  constructor(url: string, authFrame: ClientCallMessage, callbacks: CallSocketCallbacks) {
    this.url = url;
    this.authFrame = authFrame;
    this.callbacks = callbacks;
  }

  connect(): void {
    this.setStatus("connecting");
    const socket = new WebSocket(this.url);
    socket.binaryType = "arraybuffer";
    this.socket = socket;

    socket.addEventListener("open", () => {
      // The auth frame must be the first frame sent on this connection.
      this.sendJson(this.authFrame);
      this.setStatus("open");
    });

    socket.addEventListener("message", (event) => {
      if (typeof event.data === "string") {
        this.handleTextFrame(event.data);
      } else if (event.data instanceof ArrayBuffer) {
        this.callbacks.onAudioFrame(event.data);
      }
    });

    socket.addEventListener("error", () => {
      this.callbacks.onSocketError("The call connection had a problem.");
    });

    socket.addEventListener("close", () => {
      this.setStatus("closed");
    });
  }

  private handleTextFrame(data: string): void {
    let parsed: unknown;
    try {
      parsed = JSON.parse(data);
    } catch {
      this.callbacks.onSocketError("Received an unreadable message from the call service.");
      return;
    }
    const message = parseServerCallMessage(parsed);
    if (message) {
      this.callbacks.onMessage(message);
    }
  }

  private setStatus(status: CallSocketStatus): void {
    this.status = status;
    this.callbacks.onStatusChange(status);
  }

  private sendJson(message: ClientCallMessage): void {
    this.socket?.send(JSON.stringify(message));
  }

  /** Sends a typed text turn (text-input mode, or headless/prerecorded test mode). */
  sendTextTurn(text: string): void {
    this.sendJson({ type: "text_turn", text, timestamp: new Date().toISOString() });
  }

  /** Sends a raw PCM16 24 kHz mono microphone frame. */
  sendAudioFrame(frame: ArrayBuffer): void {
    if (this.socket?.readyState === WebSocket.OPEN) {
      this.socket.send(frame);
    }
  }

  sendMicState(muted: boolean): void {
    this.sendJson({ type: "mic_state", muted });
  }

  sendConfirmationResponse(confirmationId: string, approved: boolean): void {
    this.sendJson({ type: "confirmation_response", confirmationId, approved });
  }

  /** Barge-in: asks the backend to stop sending/queuing further output. Does not claim to roll
   * back any business mutation already committed. */
  sendCancelOutput(): void {
    this.sendJson({ type: "cancel_output" });
  }

  sendEndCall(): void {
    this.sendJson({ type: "end_call" });
  }

  close(): void {
    this.socket?.close();
    this.socket = null;
  }

  getStatus(): CallSocketStatus {
    return this.status;
  }
}
