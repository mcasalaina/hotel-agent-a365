import styles from "./DispositionBanner.module.css";
import type { DispositionInfo } from "../hooks/callSessionReducer";

interface DispositionBannerProps {
  disposition: DispositionInfo;
}

const OUTCOME_LABEL: Record<DispositionInfo["outcome"], string> = {
  resolved: "Resolved",
  escalated: "Escalated",
  cancelled: "Cancelled",
  error: "Ended with an error",
};

const OUTCOME_CLASS: Record<DispositionInfo["outcome"], string> = {
  resolved: "outcomeResolved",
  escalated: "outcomeEscalated",
  cancelled: "outcomeCancelled",
  error: "outcomeError",
};

/** Final call disposition, shown once the agent has wrapped up. */
export function DispositionBanner({ disposition }: DispositionBannerProps) {
  return (
    <div
      className={`${styles.banner} ${styles[OUTCOME_CLASS[disposition.outcome]]}`}
      role="status"
      aria-live="polite"
    >
      <p className={styles.title}>{OUTCOME_LABEL[disposition.outcome]}</p>
      <p>{disposition.summary}</p>
    </div>
  );
}
