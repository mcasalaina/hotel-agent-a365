import styles from "./ConfirmationCard.module.css";
import type { ConfirmationEntry } from "../hooks/callSessionReducer";

interface ConfirmationCardProps {
  confirmation: ConfirmationEntry;
  onRespond: (confirmationId: string, approved: boolean) => void;
}

/** A pending mutation confirmation. Every mutation the agent proposes requires this on-screen
 * approval (in addition to any spoken confirmation) before it proceeds. */
export function ConfirmationCard({ confirmation, onRespond }: ConfirmationCardProps) {
  const isResolved = confirmation.resolvedApproved !== null;

  return (
    <div className={styles.card} role="group" aria-labelledby={`confirmation-${confirmation.id}`}>
      <p className={styles.heading} id={`confirmation-${confirmation.id}`}>
        Confirmation needed
      </p>
      <p className={styles.summary}>{confirmation.summary}</p>
      <dl className={styles.details}>
        {Object.entries(confirmation.details).map(([key, value]) => (
          <div key={key} style={{ display: "contents" }}>
            <dt className={styles.detailKey}>{key}</dt>
            <dd className={styles.detailValue}>{value}</dd>
          </div>
        ))}
      </dl>
      {isResolved ? (
        <p className={styles.resolvedNote}>
          {confirmation.resolvedApproved ? "You approved this change." : "You declined this change."}
        </p>
      ) : (
        <div className={styles.actions}>
          <button
            type="button"
            className={styles.approveButton}
            onClick={() => onRespond(confirmation.confirmationId, true)}
          >
            Approve
          </button>
          <button
            type="button"
            className={styles.declineButton}
            onClick={() => onRespond(confirmation.confirmationId, false)}
          >
            Decline
          </button>
        </div>
      )}
    </div>
  );
}
