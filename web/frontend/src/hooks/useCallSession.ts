/**
 * Orchestrates a single simulated call: acquiring a backend session handle, opening the call
 * socket, wiring microphone capture and agent audio playback, and reducing the incoming event
 * stream into UI state. Also supports an explicit headless/demo mode that plays back a
 * deterministic scripted event stream with no network activity at all, per the Phase 3
 * headless/prerecorded test-mode requirement.
 *
 * Mutable cross-callback state (the config, the current reconnect attempt, whether the guest
 * ended the call intentionally) lives in refs rather than `useState`/`useCallback` dependency
 * arrays. This keeps `connectSocket` and `scheduleReconnect` stable, single-identity callbacks
 * that always read the latest values instead of risking a stale closure across renders.
 */
import { useCallback, useEffect, useReducer, useRef } from "react";
import { useAuth } from "../auth/authContext";
import { buildCallSocketUrl, createCallSession, fetchBackendConfig } from "../lib/backendClient";
import { AudioPlaybackQueue } from "../lib/audioPlayback";
import { type AudioCaptureHandle, startAudioCapture } from "../lib/audioCapture";
import { CallSocket } from "../lib/callSocket";
import { buildDemoScenario } from "../lib/demoScenario";
import { generateSilentPcmFrame } from "../lib/pcm";
import { chunkPcm16, decodePcmWave } from "../lib/wav";
import type { BackendConfigResponse, CreateSessionResponse } from "../types/protocol";
import { callSessionReducer, initialCallSessionState, type CallMode } from "./callSessionReducer";

export interface UseCallSessionResult {
  state: ReturnType<typeof callSessionReducer>;
  config: BackendConfigResponse | null;
  configError: string | null;
  startCall: (mode: CallMode) => Promise<void>;
  startPrerecorded: (file: File) => Promise<void>;
  sendText: (text: string) => void;
  toggleMute: () => void;
  endCall: () => void;
  bargeIn: () => void;
  respondToConfirmation: (confirmationId: string, approved: boolean) => void;
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

export function useCallSession(): UseCallSessionResult {
  const { acquireApiToken } = useAuth();
  const [state, dispatch] = useReducer(callSessionReducer, initialCallSessionState);
  const [configState, setConfigState] = useReducer(
    (
      _current: { config: BackendConfigResponse | null; error: string | null },
      next: { config: BackendConfigResponse | null; error: string | null },
    ) => next,
    { config: null, error: null },
  );

  const socketRef = useRef<CallSocket | null>(null);
  const connectSocketRef = useRef<
    ((mode: CallMode, session: CreateSessionResponse, websocketPath: string, isReconnect: boolean) => void) | null
  >(null);
  const audioCaptureRef = useRef<AudioCaptureHandle | null>(null);
  const playbackRef = useRef<AudioPlaybackQueue | null>(null);
  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const demoAbortRef = useRef<{ cancelled: boolean } | null>(null);
  const pendingPrerecordedRef = useRef<ArrayBuffer | null>(null);

  // Mutable snapshots kept current on every render so stable callbacks below never see stale
  // values without needing to be re-created (and re-subscribed) on every state change.
  const configRef = useRef(configState);
  configRef.current = configState;
  const modeRef = useRef<CallMode | null>(state.mode);
  modeRef.current = state.mode;
  const micMutedRef = useRef(state.micMuted);
  micMutedRef.current = state.micMuted;
  const reconnectAttemptRef = useRef(state.reconnectAttempt);
  reconnectAttemptRef.current = state.reconnectAttempt;
  const userEndedRef = useRef(false);

  useEffect(() => {
    let cancelled = false;
    fetchBackendConfig()
      .then((loaded) => {
        if (!cancelled) {
          setConfigState({ config: loaded, error: null });
        }
      })
      .catch(() => {
        if (!cancelled) {
          setConfigState({
            config: null,
            error: "Unable to reach the contact-center backend configuration endpoint.",
          });
        }
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const teardown = useCallback(() => {
    if (reconnectTimerRef.current) {
      clearTimeout(reconnectTimerRef.current);
      reconnectTimerRef.current = null;
    }
    audioCaptureRef.current?.stop();
    audioCaptureRef.current = null;
    playbackRef.current?.dispose();
    playbackRef.current = null;
    socketRef.current?.close();
    socketRef.current = null;
    pendingPrerecordedRef.current = null;
    if (demoAbortRef.current) {
      demoAbortRef.current.cancelled = true;
      demoAbortRef.current = null;
    }
  }, []);

  // Tear down any open call/audio resources when the component using this hook unmounts.
  useEffect(() => teardown, [teardown]);

  const scheduleReconnect = useCallback(
    (mode: CallMode, session: CreateSessionResponse, websocketPath: string) => {
      const config = configRef.current.config;
      if (userEndedRef.current || !config) {
        return;
      }
      const attempt = reconnectAttemptRef.current + 1;
      if (attempt > config.maxReconnectAttempts) {
        dispatch({
          type: "LOCAL_ERROR",
          message: "Unable to reconnect the call after several attempts.",
        });
        return;
      }
      dispatch({ type: "RECONNECT_ATTEMPT", attempt });
      const backoff = config.reconnectBackoffMs * 2 ** (attempt - 1);
      reconnectTimerRef.current = setTimeout(() => {
        connectSocketRef.current?.(mode, session, websocketPath, true);
      }, backoff);
    },
    [],
  );

  const connectSocket = useCallback(
    (mode: CallMode, session: CreateSessionResponse, websocketPath: string, isReconnect: boolean) => {
      const url = buildCallSocketUrl(websocketPath);
      const socket = new CallSocket(
        url,
        {
          type: "auth",
          opaqueHandle: session.sessionHandle,
          mode,
          agentSessionId: session.agentSessionId,
        },
        {
          onMessage: (message) => {
            dispatch({ type: "SERVER_MESSAGE", message });
            if (
              message.type === "auth_ack" &&
              mode === "prerecorded" &&
              pendingPrerecordedRef.current
            ) {
              const pcm = pendingPrerecordedRef.current;
              pendingPrerecordedRef.current = null;
              for (const frame of chunkPcm16(pcm)) {
                socket.sendAudioFrame(frame);
              }
              socket.sendAudioCommit();
            }
          },
          onAudioFrame: (frame) => playbackRef.current?.enqueue(frame),
          onStatusChange: () => {
            /* connection lifecycle is surfaced via call_state messages, not raw socket state */
          },
          onSocketError: () => {
            dispatch({
              type: "LOCAL_ERROR",
              message: "The call connection had a problem. Attempting to reconnect...",
            });
            scheduleReconnect(mode, session, websocketPath);
          },
        },
      );
      socket.connect();
      socketRef.current = socket;
      if (!isReconnect) {
        playbackRef.current = new AudioPlaybackQueue();
      }
    },
    [scheduleReconnect],
  );
  connectSocketRef.current = connectSocket;

  const runDemoScenario = useCallback(() => {
    const abortToken = { cancelled: false };
    demoAbortRef.current = abortToken;
    dispatch({ type: "PHASE_CHANGE", phase: "connecting" });

    // Headless/prerecorded test mode never requests microphone permission. To still exercise the
    // outbound-audio code path end to end, it generates one short silent PCM16 24 kHz mono frame
    // exactly as `startAudioCapture` would produce from a live microphone, and reports it on the
    // timeline the same way a real sent frame would be acknowledged.
    const silentFrame = generateSilentPcmFrame();
    dispatch({
      type: "SERVER_MESSAGE",
      message: {
        type: "timeline_event",
        category: "progress",
        message: `Prepared a ${silentFrame.byteLength}-byte silent audio frame for offline playback (no microphone used).`,
        timestamp: new Date().toISOString(),
      },
    });

    (async () => {
      const steps = buildDemoScenario();
      for (const step of steps) {
        if (abortToken.cancelled) {
          return;
        }
        await sleep(step.delayMs);
        if (abortToken.cancelled) {
          return;
        }
        dispatch({ type: "SERVER_MESSAGE", message: step.message });
      }
    })();
  }, []);

  const startCall = useCallback(
    async (mode: CallMode) => {
      teardown();
      userEndedRef.current = false;
      dispatch({ type: "MODE_SELECTED", mode });

      const config = configRef.current.config;
      if (!config) {
        dispatch({ type: "LOCAL_ERROR", message: "Contact-center configuration is not ready yet." });
        return;
      }

      if (mode === "headless") {
        if (!config.features.offlinePlaybackEnabled) {
          dispatch({ type: "LOCAL_ERROR", message: "Offline playback is not available." });
          return;
        }
        runDemoScenario();
        return;
      }

      try {
        dispatch({ type: "PHASE_CHANGE", phase: "connecting" });
        const accessToken = await acquireApiToken();
        const session = await createCallSession(accessToken);
        connectSocket(mode, session, config.websocketPath, false);

        if (mode === "voice") {
          const handle = await startAudioCapture((frame) => socketRef.current?.sendAudioFrame(frame));
          if (micMutedRef.current) {
            handle.setMuted(true);
          }
          audioCaptureRef.current = handle;
        }
      } catch (err) {
        dispatch({
          type: "LOCAL_ERROR",
          message: err instanceof Error ? err.message : "Unable to start the call.",
        });
      }
    },
    [acquireApiToken, connectSocket, runDemoScenario, teardown],
  );

  const startPrerecorded = useCallback(
    async (file: File) => {
      teardown();
      userEndedRef.current = false;
      dispatch({ type: "MODE_SELECTED", mode: "prerecorded" });
      const config = configRef.current.config;
      if (!config?.features.prerecordedAudioEnabled) {
        dispatch({
          type: "LOCAL_ERROR",
          message: "Prerecorded audio is not enabled by the backend.",
        });
        return;
      }

      try {
        const pcm = decodePcmWave(await file.arrayBuffer());
        pendingPrerecordedRef.current = pcm;
        dispatch({ type: "PHASE_CHANGE", phase: "connecting" });
        const accessToken = await acquireApiToken();
        const session = await createCallSession(accessToken);
        connectSocket("prerecorded", session, config.websocketPath, false);
      } catch (err) {
        pendingPrerecordedRef.current = null;
        dispatch({
          type: "LOCAL_ERROR",
          message: err instanceof Error ? err.message : "Unable to load the prerecorded prompt.",
        });
      }
    },
    [acquireApiToken, connectSocket, teardown],
  );

  const sendText = useCallback((text: string) => {
    const trimmed = text.trim();
    if (!trimmed) {
      return;
    }
    if (modeRef.current === "headless") {
      // Headless/demo mode never talks to a real backend; typed turns are echoed locally as a
      // synthetic user transcript entry so the send-text code path can still be exercised.
      dispatch({
        type: "SERVER_MESSAGE",
        message: {
          type: "transcript",
          speaker: "user",
          text: trimmed,
          isFinal: true,
          timestamp: new Date().toISOString(),
        },
      });
      return;
    }
    socketRef.current?.sendTextTurn(trimmed);
  }, []);

  const toggleMute = useCallback(() => {
    const muted = !micMutedRef.current;
    dispatch({ type: "SET_MIC_MUTED", muted });
    audioCaptureRef.current?.setMuted(muted);
    socketRef.current?.sendMicState(muted);
  }, []);

  const endCall = useCallback(() => {
    userEndedRef.current = true;
    if (modeRef.current === "headless") {
      if (demoAbortRef.current) {
        demoAbortRef.current.cancelled = true;
      }
      dispatch({ type: "PHASE_CHANGE", phase: "ended" });
      return;
    }
    socketRef.current?.sendEndCall();
    teardown();
    dispatch({ type: "PHASE_CHANGE", phase: "ended" });
  }, [teardown]);

  const bargeIn = useCallback(() => {
    playbackRef.current?.clear();
    if (modeRef.current === "headless") {
      return;
    }
    socketRef.current?.sendCancelOutput();
  }, []);

  const respondToConfirmation = useCallback((confirmationId: string, approved: boolean) => {
    // Optimistically mark the card resolved immediately so it disables without waiting on a
    // round trip; the backend remains the source of truth for the eventual result card.
    dispatch({ type: "CONFIRMATION_RESOLVED", confirmationId, approved });
    if (modeRef.current === "headless") {
      return;
    }
    socketRef.current?.sendConfirmationResponse(confirmationId, approved);
  }, []);

  return {
    state,
    config: configState.config,
    configError: configState.error,
    startCall,
    startPrerecorded,
    sendText,
    toggleMute,
    endCall,
    bargeIn,
    respondToConfirmation,
  };
}
