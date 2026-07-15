import styles from "./CallStatusBar.module.css";
import type { CallMode, CallPhase } from "../hooks/callSessionReducer";

interface CallStatusBarProps {
  phase: CallPhase;
  mode: CallMode | null;
  elapsedLabel: string;
  reconnectAttempt: number;
  micMuted: boolean;
}

const PHASE_LABEL: Record<CallPhase, string> = {
  idle: "Not on a call",
  starting: "Starting call\u2026",
  connecting: "Connecting\u2026",
  active: "Call active",
  reconnecting: "Reconnecting\u2026",
  ended: "Call ended",
  error: "Connection error",
};

const PHASE_CLASS: Record<CallPhase, string> = {
  idle: "badgeIdle",
  starting: "badgeConnecting",
  connecting: "badgeConnecting",
  active: "badgeActive",
  reconnecting: "badgeReconnecting",
  ended: "badgeEnded",
  error: "badgeError",
};

export function CallStatusBar({ phase, mode, elapsedLabel, reconnectAttempt, micMuted }: CallStatusBarProps) {
  const badgeClass = `${styles.badge} ${styles[PHASE_CLASS[phase]]}`;
  return (
    <div className={styles.statusBar} role="status" aria-live="polite">
      <span className={badgeClass}>
        <span className={styles.badgeDot} aria-hidden="true" />
        {PHASE_LABEL[phase]}
        {mode ? ` \u2022 ${mode} mode` : ""}
      </span>
      {phase === "active" || phase === "reconnecting" ? (
        <span className={styles.elapsed} aria-label="Elapsed call time">
          {elapsedLabel}
        </span>
      ) : null}
      {phase === "reconnecting" ? (
        <span className={styles.reconnectNote}>Reconnect attempt {reconnectAttempt}&hellip;</span>
      ) : null}
      {micMuted && phase === "active" ? <span className={styles.mutedNote}>Microphone muted</span> : null}
    </div>
  );
}
