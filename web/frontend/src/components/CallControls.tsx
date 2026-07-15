import styles from "./CallControls.module.css";
import type { CallMode, CallPhase } from "../hooks/callSessionReducer";
import type { BackendConfigResponse } from "../types/protocol";

interface CallControlsProps {
  phase: CallPhase;
  mode: CallMode | null;
  micMuted: boolean;
  features: BackendConfigResponse["features"] | null;
  onStartCall: (mode: CallMode) => void;
  onToggleMute: () => void;
  onBargeIn: () => void;
  onEndCall: () => void;
}

const isCallLive = (phase: CallPhase) =>
  phase === "starting" || phase === "connecting" || phase === "active" || phase === "reconnecting";

export function CallControls({
  phase,
  mode,
  micMuted,
  features,
  onStartCall,
  onToggleMute,
  onBargeIn,
  onEndCall,
}: CallControlsProps) {
  const callLive = isCallLive(phase);

  if (!callLive) {
    return (
      <section className={styles.panel} aria-labelledby="call-controls-heading">
        <h2 className={styles.heading} id="call-controls-heading">
          Start a call
        </h2>
        <div className={styles.modeRow}>
          <button
            type="button"
            className={styles.modeButton}
            onClick={() => onStartCall("voice")}
            disabled={features ? !features.voiceEnabled : false}
          >
            Start voice call
          </button>
          <button
            type="button"
            className={styles.modeButton}
            onClick={() => onStartCall("text")}
            disabled={features ? !features.textEnabled : false}
          >
            Start text call
          </button>
          <button
            type="button"
            className={styles.modeButton}
            onClick={() => onStartCall("headless")}
            disabled={features ? !features.headlessDemoEnabled : false}
          >
            Run headless demo
          </button>
        </div>
        <p className={styles.hint}>
          Headless demo mode plays a scripted, synthetic call with no microphone and no network
          connection, useful for validating the interface without a live backend.
        </p>
      </section>
    );
  }

  return (
    <section className={styles.panel} aria-labelledby="call-controls-heading">
      <h2 className={styles.heading} id="call-controls-heading">
        Call controls
      </h2>
      <div className={styles.activeControls}>
        {mode === "voice" ? (
          <button
            type="button"
            className={`${styles.controlButton} ${micMuted ? styles.controlButtonActive : ""}`}
            onClick={onToggleMute}
            aria-pressed={micMuted}
          >
            {micMuted ? "Unmute microphone" : "Mute microphone"}
          </button>
        ) : null}
        <button type="button" className={styles.controlButton} onClick={onBargeIn}>
          Interrupt agent
        </button>
        <button type="button" className={styles.endCallButton} onClick={onEndCall}>
          End call
        </button>
      </div>
      <p className={styles.hint}>
        &ldquo;Interrupt agent&rdquo; stops the agent&rsquo;s current audio/text output right away. It does
        not undo any change the agent has already saved.
      </p>
    </section>
  );
}
